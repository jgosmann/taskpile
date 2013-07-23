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
        urwid.GridFlow.__init__(self, buttons, cell_width, 2, 0, 'center')


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
        if key == 'enter':
            self._on_btn_click(self._ok_btn)
        elif key == 'esc':
            self._on_btn_click(self._cancel_btn)
        else:
            return super(Dialog, self).keypress(size, key)


class NewTaskInputs(urwid.ListBox):
    def __init__(self):
        self.name = urwid.Edit("Task name: ")
        self.command = urwid.Edit("Command: ")
        self._walker = urwid.SimpleFocusListWalker([self.name, self.command])
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
        Dialog.__init__(self, parent, NewTaskInputs())


class TaskView(urwid.Columns):
    state_indicators = {
        State.PENDING: ' ',
        State.RUNNING: 'R',
        State.FINISHED: 'F',
        State.STOPPED: 'S'
    }

    def __init__(self, task):
        self.task = task
        self.state = urwid.Text(
            self.state_indicators[self.task.state], wrap='clip')
        self.pid = urwid.Text(str(self.task.pid), 'right', wrap='clip')
        self.name = urwid.Text(self.task.name, wrap='clip')
        super(TaskView, self).__init__([
            (6, self.pid), (1, self.state), self.name], 1)

    def selectable(self):
        return True


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
            urwid.LineBox(urwid.Padding(self.tasklist, left=1, right=1)),
            ('pack', ButtonPane([add_task_btn, exit_btn]))]))

    def on_add_task_btn_clicked(self, btn):
        dialog = NewTaskDialog(self)

        def callback():
            self.taskpile.enqueue(Task(lambda: None))
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
    m = MainWindow()
    loop = urwid.MainLoop(m)
    invoke_update(loop, (1, m))
    loop.run()
