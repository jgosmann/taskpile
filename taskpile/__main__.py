import urwid


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
        w = urwid.Pile([body, ('pack', ButtonPane(
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
            return key


class NewTaskInputs(urwid.ListBox):
    def __init__(self):
        self.name = urwid.Edit("Task name: ")
        self.command = urwid.Edit("Command: ")
        urwid.ListBox.__init__(self, urwid.SimpleFocusListWalker(
            [self.name, self.command]))


class NewTaskDialog(Dialog):
    def __init__(self, parent):
        Dialog.__init__(self, parent, NewTaskInputs())


class MainWindow(urwid.WidgetPlaceholder):
    def __init__(self):
        add_task_btn = urwid.Button("Add task ...")
        exit_btn = urwid.Button("Exit")
        self.exit_btn = exit_btn

        urwid.connect_signal(
            add_task_btn, 'click', self.on_add_task_btn_clicked)
        urwid.connect_signal(exit_btn, 'click', self.on_exit_btn_clicked)

        urwid.WidgetPlaceholder.__init__(self, urwid.Pile([
            urwid.LineBox(urwid.Filler(urwid.Text("Task list"))),
            ('pack', ButtonPane([add_task_btn, exit_btn]))]))

    def on_add_task_btn_clicked(self, btn):
        dialog = NewTaskDialog(self)

        def callback():
            pass

        urwid.connect_signal(dialog, 'ok', callback)
        dialog.show()

    def on_exit_btn_clicked(self, btn):
        raise urwid.ExitMainLoop()

if __name__ == '__main__':
    urwid.MainLoop(MainWindow()).run()
