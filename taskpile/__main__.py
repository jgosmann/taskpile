import subprocess

import urwid

from taskpile import State, Task, Taskpile


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
    def __init__(self, buttons):
        cell_width = max(len(b.label) for b in buttons) + 4
        urwid.GridFlow.__init__(
            self, [urwid.AttrMap(b, None, 'focus') for b in buttons],
            cell_width, 2, 0, 'center')


class ModalWidget(urwid.WidgetPlaceholder):
    def __init__(self, parent, body):
        self.parent = parent
        self.original_widget = body
        self.__bottom_widget = getattr(self.parent, 'original_widget')

    def show(self):
        setattr(self.parent, 'original_widget', self)

    def hide(self):
        setattr(self.parent, 'original_widget', self.__bottom_widget)

    def set_parent(self, parent):
        assert hasattr(parent, 'original_widget')
        self._parent = parent

    def get_parent(self):
        return self._parent

    parent = property(get_parent, set_parent)


class Dialog(ModalWidget):
    __metaclass__ = urwid.MetaSignals
    signals = ['ok', 'cancel']

    def __init__(self, parent, body, ok_label='OK', cancel_label='Cancel'):
        self._ok_btn = urwid.Button(ok_label)
        self._cancel_btn = urwid.Button(cancel_label)
        w = Pile([body, ('pack', ButtonPane(
            [self._ok_btn, self._cancel_btn]))])
        w = urwid.Padding(w, left=1, right=1)
        w = urwid.LineBox(w)
        ModalWidget.__init__(self, parent, w)

        urwid.connect_signal(self._ok_btn, 'click', self._on_btn_click)
        urwid.connect_signal(self._cancel_btn, 'click', self._on_btn_click)

        self._signal_map = {self._ok_btn: 'ok', self._cancel_btn: 'cancel'}

    def _on_btn_click(self, btn):
        try:
            urwid.emit_signal(self, self._signal_map[btn])
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


class NewTaskInputs(urwid.ListBox):
    def __init__(self):
        self.name = urwid.Edit("Task name: ")
        self.command = urwid.Edit("Command: ")
        self._walker = urwid.SimpleFocusListWalker([self.command, self.name])
        urwid.ListBox.__init__(self, self._walker)

    def keypress(self, size, key):
        key = super(NewTaskInputs, self).keypress(size, key)
        try:
            if key == 'tab':
                self.set_focus(
                    self._walker.next_position(self.focus_position), 'above')
                key = None
                self.render(size)
            elif key == 'shift tab':
                self.set_focus(
                    self._walker.prev_position(self.focus_position), 'below')
                key = None
                self.render(size)
        except IndexError:
            pass
        return key


class NewTaskDialog(Dialog):
    def __init__(self, parent):
        self._inputs = NewTaskInputs()
        Dialog.__init__(self, parent, self._inputs)

    def get_name(self):
        if self._inputs.name.edit_text != '':
            return self._inputs.name.edit_text
        else:
            return self.command

    def get_command(self):
        return self._inputs.command.edit_text

    name = property(get_name)
    command = property(get_command)


class TaskView(urwid.AttrMap):
    state_indicators = {
        State.PENDING: ' ',
        State.RUNNING: 'Running',
        State.FINISHED: 'Finished',
        State.STOPPED: 'Stopped'
    }

    def __init__(self, task):
        self.task = task
        self.state = urwid.Text(
            self.state_indicators[self.task.state], wrap='clip')
        self.pid = urwid.Text(str(self.task.pid), 'right', wrap='clip')
        self.name = urwid.Text(self.task.name, wrap='clip')
        w = urwid.Columns([(6, self.pid), (1, self.state), self.name], 1)
        super(TaskView, self).__init__(w, None, 'focus')

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

    @staticmethod
    def create_header():
        return urwid.AttrMap(
            urwid.Columns([
                (6, urwid.Text('PID', 'right', wrap='clip')),
                (1, urwid.Text('Status', wrap='clip')),
                urwid.Text('Task name', wrap='clip')], 1),
            'tbl_header')


class TaskList(urwid.ListBox):
    def __init__(self, taskpile):
        self.taskpile = taskpile
        super(TaskList, self).__init__(urwid.SimpleFocusListWalker([]))

    def update(self):
        self.taskpile.update()
        tasks = self.taskpile.running + self.taskpile.pending + \
            self.taskpile.finished
        self.body[:] = [TaskView(t) for t in tasks]


class MainWindow(urwid.WidgetPlaceholder):
    def __init__(self):
        self.taskpile = Taskpile()

        self.tasklist = TaskList(self.taskpile)
        add_task_btn = urwid.Button("Add task ...")
        exit_btn = urwid.Button("Exit")

        urwid.connect_signal(
            add_task_btn, 'click', self.on_add_task_btn_clicked)
        urwid.connect_signal(exit_btn, 'click', self.on_exit_btn_clicked)

        urwid.WidgetPlaceholder.__init__(self, urwid.Pile([
            urwid.LineBox(urwid.Padding(
                urwid.Pile(
                    [('pack', TaskView.create_header()), self.tasklist]),
                left=1, right=1)),
            ('pack', ButtonPane([add_task_btn, exit_btn]))]))

    def on_add_task_btn_clicked(self, btn):
        dialog = NewTaskDialog(self)

        def callback():
            self.taskpile.enqueue(Task(
                subprocess.call, (dialog.command,), {'shell': True},
                dialog.name))
            self.tasklist.update()

        urwid.connect_signal(dialog, 'ok', callback)
        dialog.show()

    def on_exit_btn_clicked(self, btn):
        raise urwid.ExitMainLoop()

    def update(self):
        self.tasklist.update()


def invoke_update(loop, (interval, act_on)):
    act_on.update()
    loop.set_alarm_in(interval, invoke_update, (interval, act_on))


if __name__ == '__main__':
    palette = [
        ('focus', 'standout', ''),
        ('tbl_header', 'bold', '')
    ]
    m = MainWindow()
    loop = urwid.MainLoop(m, palette)
    invoke_update(loop, (1, m))
    loop.run()
