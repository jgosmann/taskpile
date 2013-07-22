import urwid


class Dialog(urwid.Pile):
    def __init__(self, body, ok_label='OK', cancel_label='Cancel'):
        ok_btn = urwid.Button(ok_label)
        cancel_btn = urwid.Button(cancel_label)
        urwid.Pile.__init__(self, [
            body, ('pack', urwid.Columns([ok_btn, cancel_btn]))])


class NewTaskInputs(urwid.ListBox):
    def __init__(self):
        self.name = urwid.Edit("Task name: ")
        self.command = urwid.Edit("Command: ")
        urwid.ListBox.__init__(self, urwid.SimpleFocusListWalker(
            [self.name, self.command]))


class NewTaskDialog(Dialog):
    def __init__(self):
        Dialog.__init__(self, NewTaskInputs())


class MainWindow(urwid.WidgetPlaceholder):
    def __init__(self):
        add_task_btn = urwid.Button("Add task ...")
        exit_btn = urwid.Button("Exit")

        urwid.connect_signal(
            add_task_btn, 'click', self.on_add_task_btn_clicked)
        urwid.connect_signal(exit_btn, 'click', self.on_exit_btn_clicked)

        urwid.WidgetPlaceholder.__init__(self, urwid.Pile([
            urwid.LineBox(urwid.Filler(urwid.Text("Task list"))),
            ('pack', urwid.Columns([add_task_btn, exit_btn]))]))

    def on_add_task_btn_clicked(self, btn):
        self.original_widget = NewTaskDialog()

    def on_exit_btn_clicked(self, btn):
        raise urwid.ExitMainLoop()

if __name__ == '__main__':
    urwid.MainLoop(MainWindow()).run()
