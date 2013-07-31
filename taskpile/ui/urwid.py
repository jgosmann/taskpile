from __future__ import absolute_import

import multiprocessing
import os
import os.path
import shlex
import shutil
import subprocess
from tempfile import mkstemp, TemporaryFile
from weakref import WeakKeyDictionary

import urwid

from taskpile.sanitize import quote_for_shell
from taskpile.signalnames import signalnames
from taskpile.core import State, Task, Taskpile


class ExternalTask(Task):
    def __init__(self, command, name=None, original_files={}, niceness=0):
        if name is None:
            name = command
        self.command = command
        self.original_files = original_files
        self.outbuf, self.errbuf = (TemporaryFile('w+'), TemporaryFile('w+'))
        super(ExternalTask, self).__init__(
            subprocess.call, (command,), {
                'shell': True, 'stdout': self.outbuf, 'stderr': self.errbuf},
            name, niceness=niceness)


def tabbed_focus(cls):
    orig_keypress = cls.keypress

    def keypress(self, size, key):
        key = orig_keypress(self, size, key)
        candidates = []
        if key == 'tab':
            candidates = range(self.focus_position + 1, len(self.contents))
        elif key == 'shift tab' and self.focus_position > 0:
            candidates = range(self.focus_position - 1, -1, -1)

        for candidate in candidates:
            if self.contents[candidate][0].selectable():
                self.focus_position = candidate
                return
        return key

    cls.keypress = keypress
    return cls


Pile = tabbed_focus(urwid.Pile)


@tabbed_focus
class ButtonPane(urwid.GridFlow):
    def __init__(self, buttons, align='center'):
        cell_width = max(len(b.label) for b in buttons) + 4
        urwid.GridFlow.__init__(
            self, [urwid.AttrMap(b, None, 'focus') for b in buttons],
            cell_width, 2, 0, align)


class ModalWidget(urwid.WidgetPlaceholder):
    mainloop = None

    def __init__(self, original_widget, width, height):
        self.original_widget = original_widget
        self.width = width
        self.height = height
        self.__visible = False

    def show(self):
        if not self.__visible:
            self.__bottom_widget = getattr(self.mainloop, 'widget')
            self.__visible = True
            w = urwid.Overlay(
                self, self.__bottom_widget, 'center', self.width,
                'middle', self.height)
            setattr(self.mainloop, 'widget', w)

    def hide(self):
        if self.__visible:
            setattr(self.mainloop, 'widget', self.__bottom_widget)
            self.__visible = False
            self.__bottom_widget = None

    visible = property(lambda self: self.__visible)


class Dialog(ModalWidget):
    __metaclass__ = urwid.MetaSignals
    signals = ['ok', 'cancel']

    def __init__(
            self, body, width, height, ok_label='OK', cancel_label='Cancel'):
        self._ok_btn = urwid.Button(ok_label)
        self._cancel_btn = urwid.Button(cancel_label)
        w = Pile([body, ('pack', ButtonPane(
            [self._ok_btn, self._cancel_btn]))])
        w = urwid.Padding(w, left=1, right=1)
        w = urwid.LineBox(w)
        ModalWidget.__init__(self, w, width, height)

        urwid.connect_signal(self._ok_btn, 'click', self._on_btn_click)
        urwid.connect_signal(self._cancel_btn, 'click', self._on_btn_click)

        self._signal_map = {self._ok_btn: 'ok', self._cancel_btn: 'cancel'}

    def _on_btn_click(self, btn):
        try:
            if urwid.emit_signal(self, self._signal_map[btn]):
                return
        except KeyError:
            pass
        self.hide()

    def keypress(self, size, key):
        key = super(Dialog, self).keypress(size, key)
        if key == 'enter':
            self._on_btn_click(self._ok_btn)
            key = None
        elif key == 'esc':
            self._on_btn_click(self._cancel_btn)
            key = None
        return key


class IntEditWithNegNumbers(urwid.Edit):
    def keypress(self, size, key):
        if key == '-' and self.edit_pos != 0:
            return None

        if len(key) == 1 and key not in '-0123456789':
            return key

        return super(IntEditWithNegNumbers, self).keypress(size, key)


class NewTaskInputs(urwid.ListBox):
    def __init__(self, template=None):
        self.__split_command = []
        self.original_files = {}
        self.name = urwid.Edit("Task name: ")
        self.command = urwid.Edit("Command: ")
        self._command_attr_map = urwid.AttrMap(self.command, 'failure')
        self.niceness = IntEditWithNegNumbers("Niceness: ", '20')
        self._niceness_attr_map = urwid.AttrMap(self.niceness, None)
        controls = [self._command_attr_map, self.name, self._niceness_attr_map]
        self._num_fixed_elements = len(controls)
        walker = urwid.SimpleFocusListWalker(controls)
        urwid.connect_signal(self.command, 'change', self._on_command_change)
        urwid.connect_signal(self.niceness, 'change', self._on_niceness_change)
        urwid.ListBox.__init__(self, walker)

        if template is not None:
            self.init_from_template(template)

    def init_from_template(self, template):
        self.original_files = template.original_files
        self.command.set_edit_text(template.command)
        if template.command != template.name:
            self.name.set_edit_text(template.name)
        for i, f in enumerate(self._get_files(), 1):
            if f in self.original_files:
                copy = self._create_tmp_file_for(self.original_files[f])
                shutil.copyfile(f, copy)
                self.original_files[copy] = self.original_files[f]
                del self.original_files[f]
                self.set_arg(i, copy)

    def keypress(self, size, key):
        key = super(NewTaskInputs, self).keypress(size, key)
        try:
            if key == 'tab':
                self.set_focus(
                    self.body.next_position(self.focus_position), 'above')
                key = None
                self.render(size)
            elif key == 'shift tab':
                self.set_focus(
                    self.body.prev_position(self.focus_position), 'below')
                key = None
                self.render(size)
        except IndexError:
            pass
        return key

    def _get_files(self):
        return filter(os.path.isfile, self.split_command)

    def _on_command_change(self, edit, text):
        if text == '':
            self._command_attr_map.set_attr_map({None: 'failure'})
        else:
            self._command_attr_map.set_attr_map({'failure': None})

        try:
            self.__split_command = shlex.split(text)
        except ValueError:
            return  # Ignore string which cannot be parsed

        files = self._get_files()
        self.body[self._num_fixed_elements:] = [
            self._create_edit_controls_for_file(i, f)
            for i, f in enumerate(files)]

    def _create_edit_controls_for_file(self, idx, file):
        if file in self.original_files:
            edit = urwid.Button("Edit '%s' ..." % file)
            urwid.connect_signal(
                edit, 'click', self._make_edited_copy, (idx + 1, file))
            reset = urwid.Button("Reset")
            urwid.connect_signal(
                reset, 'click', self._reset_copied_file, (idx + 1, file))
            return ButtonPane([edit, reset], 'left')
        else:
            btn = urwid.Button("Replace '%s' by edited copy ..." % file)
            urwid.connect_signal(
                btn, 'click', self._make_edited_copy, (idx + 1, file))
            return urwid.AttrMap(btn, None, 'focus')

    def _make_edited_copy(self, btn, arg_data):
        idx, filename = arg_data
        if filename not in self.original_files:
            filename = self._make_copy(idx, filename)
        self._edit(filename)

    def _edit(self, filename):
        if subprocess.call([os.environ['EDITOR'], filename]) != 0:
            pass  # FIXME show STDERR

    @staticmethod
    def _create_tmp_file_for(filename):
        prefix, suffix = os.path.splitext(os.path.basename(filename))
        fd, path = mkstemp(
            prefix=prefix + '.', suffix=suffix, dir=os.getcwd())
        os.close(fd)
        return os.path.relpath(path)

    def _make_copy(self, idx, filename):
        path = self._create_tmp_file_for(filename)
        shutil.copyfile(filename, path)
        self.original_files[path] = filename
        self.set_arg(idx, path)
        return path

    def _reset_copied_file(self, btn, arg_data):
        idx, filename = arg_data
        if filename in self.original_files:
            os.unlink(filename)
            self.set_arg(idx, self.original_files[filename])

    def get_split_command(self):
        return tuple(self.__split_command)

    def set_split_command(self, value):
        self.command.set_edit_text(' '.join(
            quote_for_shell(arg) for arg in value))

    split_command = property(get_split_command, set_split_command)

    def set_arg(self, idx, value):
        self.__split_command[idx] = value
        self.command.set_edit_text(' '.join(
            quote_for_shell(arg) for arg in self.__split_command))

    def _on_niceness_change(self, w, value):
        try:
            value = int(value)
        except ValueError:
            self._niceness_attr_map.set_attr_map({None: 'failure'})
            return
        self._niceness_attr_map.set_attr_map({'failure': None})

    def validate(self):
        if self.command.edit_text == '':
            raise InputValidationError('Empty command string.')
        try:
            int(self.niceness.edit_text)
        except ValueError:
            raise InputValidationError('Invalid niceness.')


class InputValidationError(Exception):
    pass


class NewTaskDialog(Dialog):
    def __init__(self, template=None):
        self._inputs = NewTaskInputs(template)
        Dialog.__init__(
            self, self._inputs, ('relative', 100), ('relative', 100))

    def validate(self):
        self._inputs.validate()

    def get_name(self):
        if self._inputs.name.edit_text != '':
            return self._inputs.name.edit_text
        else:
            return self.command

    def get_command(self):
        return self._inputs.command.edit_text

    def get_original_files(self):
        return self._inputs.original_files

    def get_niceness(self):
        return int(self._inputs.niceness.edit_text)

    name = property(get_name)
    command = property(get_command)
    original_files = property(get_original_files)
    niceness = property(get_niceness)


class TaskView(urwid.AttrMap):
    state_indicators = {
        State.PENDING: ' ',
        State.RUNNING: 'Running',
        State.FINISHED: 'Done',
        State.STOPPED: 'Stopped'
    }

    def __init__(self, task):
        self.task = task
        self.state = urwid.Text('', wrap='clip')
        self.pid = urwid.Text('', 'right', wrap='clip')
        self.name = urwid.Text('', wrap='clip')
        w = urwid.Columns([(6, self.pid), (1, self.state), self.name], 1)
        super(TaskView, self).__init__(w, None, 'focus')
        self.update()

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == 'k':
            def terminate():
                self.task.terminate()
                self.update()

            confirm_diag = Dialog(urwid.Filler(urwid.Padding(urwid.Text(
                "Are you sure, that you want to kill the task '%s'?" %
                self.task.name))), ('relative', 75), ('relative', 25),
                'Yes', 'No')
            urwid.connect_signal(confirm_diag, 'ok', terminate)
            confirm_diag.show()
            return None
        else:
            return key

    def update(self):
        self.state.set_text(self.state_indicators[self.task.state])
        self.pid.set_text(str(self.task.pid))
        exitcode_str = ''
        if self.task.exitcode is not None:
            if self.task.exitsignal is not None and self.task.exitsignal != 0:
                exitcode_str = '[%i, %s] ' % (
                    self.task.exitcode, signalnames[self.task.exitsignal])
            else:
                exitcode_str = '[%i] ' % self.task.exitcode
            if self.task.exitcode == 0:
                if self.task.exitsignal == 0:
                    self.set_attr_map({None: 'success'})
                else:
                    self.set_attr_map({None: 'warning'})
            else:
                self.set_attr_map({None: 'failure'})
        self.name.set_text(exitcode_str + self.task.name)

    @staticmethod
    def create_header():
        return urwid.AttrMap(
            urwid.Columns([
                (6, urwid.Text('PID', 'right', wrap='clip')),
                (1, urwid.Text('Status', wrap='clip')),
                urwid.Text('Task', wrap='clip')], 1),
            'tbl_header')


class FileWalker(urwid.ListWalker):
    def __init__(self, file):
        self.file = file
        self.focus = 0
        super(FileWalker, self).__init__()
        self.move_to_end()

    def __getitem__(self, position):
        self.file.seek(0, 0)
        for i in range(position + 1):
            line = self.file.readline()
            if line == '':
                raise IndexError()
        return urwid.Text(line.rstrip())

    def next_position(self, position):
        self[position + 1]  # check if position is valid
        return position + 1

    def prev_position(self, position):
        if position < 1:
            raise IndexError()
        return position - 1

    def set_focus(self, position):
        self.focus = position
        self._modified()

    def move_to_end(self):
        try:
            while True:
                self.set_focus(self.next_position(self.focus))
        except IndexError:
            pass


class IOView(ModalWidget):
    def __init__(self, title, stdout, stderr):
        self.stdout = urwid.ListBox(FileWalker(stdout))
        self.stderr = urwid.ListBox(FileWalker(stderr))

        title = urwid.Text(('title', title))
        bgroup = []
        stdout_btn = urwid.RadioButton(
            bgroup, 'stdout', on_state_change=self.on_stdout_btn_change)
        stderr_btn = urwid.RadioButton(
            bgroup, 'stderr', on_state_change=self.on_stderr_btn_change)
        buttons = ButtonPane([stdout_btn, stderr_btn], align='left')
        divider = urwid.Divider('-')
        back_btn = urwid.Button('Back')
        urwid.connect_signal(back_btn, 'click', self.on_back_btn_click)
        footer = ButtonPane([back_btn], align='left')
        self.textview = urwid.WidgetPlaceholder(self.stdout)
        w = urwid.Pile([
            ('pack', title), ('pack', buttons), ('pack', divider),
            self.textview, ('pack', divider), ('pack', footer)])
        w = urwid.LineBox(urwid.Padding(w, left=1, right=1))
        super(IOView, self).__init__(w, ('relative', 100), ('relative', 100))

    def keypress(self, size, key):
        key = super(IOView, self).keypress(size, key)
        if key == 'esc':
            self.hide()
            key = None
        return key

    def on_stdout_btn_change(self, btn, state):
        if state:
            self.textview.original_widget = self.stdout

    def on_stderr_btn_change(self, btn, state):
        if state:
            self.textview.original_widget = self.stderr

    def on_back_btn_click(self, btn):
        self.hide()


class TaskList(urwid.ListBox):
    def __init__(self, taskpile):
        self.taskpile = taskpile
        self._model_to_view = WeakKeyDictionary()
        super(TaskList, self).__init__(urwid.SimpleFocusListWalker([]))

    def update(self):
        self.taskpile.update()
        tasks = self.taskpile.running + self.taskpile.pending + \
            self.taskpile.finished[::-1]
        focus_widget, focus_pos = self.body.get_focus()
        self.body[:] = [self._get_view_for_task(t) for t in tasks]
        if focus_pos is not None:
            try:
                new_focus = self.body.index(focus_widget)
            except:
                new_focus = max(len(self.body) - 1, focus_pos)
            self.body.set_focus(new_focus)
        for view in self.body:
            view.update()

    def _get_view_for_task(self, task):
        try:
            return self._model_to_view[task]
        except KeyError:
            view = TaskView(task)
            self._model_to_view[task] = view
            return view

    def keypress(self, size, key):
        key = super(TaskList, self).keypress(size, key)
        focus_widget, focus_pos = self.body.get_focus()
        if key is None:
            return key

        if key == 'enter' and focus_widget is not None:
            IOView(
                "Output of task '%s' (%i)" %
                (focus_widget.task.name, focus_widget.task.pid),
                focus_widget.task.outbuf, focus_widget.task.errbuf).show()
            key = None
        elif key == 'a':
            self.add_task_with_dialog(NewTaskDialog())
            key = None
        elif key == 'c' and focus_widget is not None:
            self.add_task_with_dialog(NewTaskDialog(focus_widget.task))
            key = None

        return key

    def add_task_with_dialog(self, dialog):
        def callback():
            try:
                dialog.validate()
                task = ExternalTask(
                    dialog.command, dialog.name, dialog.original_files,
                    niceness=dialog.niceness)
                self.taskpile.enqueue(task)
                self.update()
            except InputValidationError:
                # FIXME show some error message
                return True

        urwid.connect_signal(dialog, 'ok', callback)
        dialog.show()


class Sidebar(urwid.Pile):
    def __init__(self, taskpile):
        self.taskpile = taskpile
        max_jobs_edit = urwid.IntEdit(
            'Max parallel tasks: ', taskpile.max_parallel)
        self._max_jobs_attr_map = urwid.AttrMap(max_jobs_edit, None)
        urwid.connect_signal(
            max_jobs_edit, 'change', self._on_max_jobs_changed)
        controls = [
            ('pack', urwid.Divider()),
            urwid.ListBox(urwid.SimpleFocusListWalker([
                self._max_jobs_attr_map
            ])),
            ('pack', urwid.Text("""
Keys:
a: Add new task
c: Copy selected task
k: Kill selected task
q: Quit
""".strip())),
            ('pack', urwid.Divider())
        ]
        super(Sidebar, self).__init__(controls)

    def _on_max_jobs_changed(self, w, value):
        value = int(value) if value != '' else -1
        if value >= 0 and value <= multiprocessing.cpu_count():
            self.taskpile.max_parallel = value
            self._max_jobs_attr_map.set_attr_map({'failure': None})
        else:
            self._max_jobs_attr_map.set_attr_map({None: 'failure'})


class MainWindow(urwid.WidgetPlaceholder):
    def __init__(self):
        self.taskpile = Taskpile()
        self.tasklist = TaskList(self.taskpile)

        left = urwid.LineBox(urwid.Pile(
            [('pack', TaskView.create_header()), self.tasklist]))
        right = Sidebar(self.taskpile)
        super(MainWindow, self).__init__(urwid.Columns([left, (22, right)], 1))

    def keypress(self, size, key):
        key = super(MainWindow, self).keypress(size, key)
        if key == 'q':
            # FIXME do not exit if processes still running
            raise urwid.ExitMainLoop()
        elif key == 'a':
            key = self.tasklist.add_task_with_dialog(NewTaskDialog())
        return key

    def update(self):
        self.tasklist.update()


def invoke_update(loop, args):
    interval, act_on = args
    act_on.update()
    loop.set_alarm_in(interval, invoke_update, (interval, act_on))


def main():
    palette = [
        ('focus', 'standout', ''),
        ('tbl_header', 'bold', ''),
        ('title', 'bold', ''),
        ('success', 'dark green', ''),
        ('warning', 'brown', ''),
        ('failure', 'dark red', '')
    ]
    m = MainWindow()
    loop = urwid.MainLoop(m, palette)
    ModalWidget.mainloop = loop
    invoke_update(loop, (1, m))
    loop.run()


if __name__ == '__main__':
    main()
