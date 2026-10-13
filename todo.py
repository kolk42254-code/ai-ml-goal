class TodoList:
    def __init__(self):
        self.tasks = []
    def add(self, task):
        self.tasks.append(task)
    def done(self, task):
        if task in self.tasks:
            self.tasks.remove(task)
            print("Done", task)
        else:
            print(task, "not in the list")

    def show(self):
        if len(self.tasks) == 0:
            return None
        for i, task in enumerate(self.tasks):
            print(i +1, task)


t = TodoList()
t.add("P29 practice")
t.add("Git hub setup")
t.add("DSA")
t.show()
t.done("Git hub setup")
t.done("sswim")
t.show()

e = TodoList()
e.show()