class Bot:
    def __init__(self, name):
        self.name = name
        self.lap_times = []

    def add_lap(self, seconds):
        self.lap_times.append(seconds)

    def total_time(self):
        total = 0
        for t in self.lap_times:
            total = total + t
        return round(total, 2)

    def best_lap(self):
        if len(self.lap_times) == 0:
            return None
        best = self.lap_times[0]
        for t in self.lap_times:
            if t < best:
                best = t
        return best


red = Bot("Red")
red.add_lap(20.5)
red.add_lap(19.8)
red.add_lap(21.0)
print(red.lap_times)
print(red.total_time())
print(red.best_lap())

blue = Bot("Blue")
print(blue.best_lap())
print("\n" * 2)

class Bankaccount:
    def __init__(self, owner):
        self.owner = owner
        self.balance = 0
        self.history=[]

    def deposit(self, amount):
        if amount > 10:
            self.balance += amount
            self.history.append(amount)
            print("Amount added successfully")
            return
        else:
            print("Amount should be greater then 10")
            return
    def withdraw(self, amount):
        if amount <=0:
            print("Amount should be more than 0")
            return
        if amount > self.balance:
            print("Not enough fund in your account")
            return
        self.balance-= amount
        self.history.append("deopsit " + str(amount))
        self.history.append("Withdrawnn amount " + str(amount))
    def show(self):
        print(f"{self.owner} has {self.balance}$")
        for h in self.history:
            print(" -", h)


a = Bankaccount("Lohi")
a.deposit(1000)
a.withdraw(500)
a.show()