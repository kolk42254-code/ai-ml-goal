import os
import subprocess
import sys
import time

# The folder this file is in, so the menu finds the animations on any computer
HERE = os.path.dirname(os.path.abspath(__file__))


def run(file_name):
    subprocess.run([sys.executable, os.path.join(HERE, file_name)])


while True:
    os.system("cls")
    op = ["Eye with heart animation", "Eye with heart animation realistic", "Eye blinking","Eye animation with beautiful Terminal", "Quit"]
    for i, j in enumerate(op, start=1):
        print(f"{i}.{j}")
    user = input("Choose the option -> ")
    os.system("cls")
    if user == "5":
        os.system("cls")
        for i in range(3, 0, -1):
            print(f"Terminating in {i}s", end="\r", flush=True)
            time.sleep(1.0)
        exit()
    for i in range(3, 0, -1):
        print(f"Launching in {i}s", end="\r", flush=True)
        time.sleep(1.0)
    try:
        os.system("cls")
        if user=="1":
            run("Eye_with_heart.py")
        elif user == "2":
            run("eye_to_space2.py")
        elif user == "3":
            run("Eye_blink.py")
        elif user == "4":
            run("eye_to_space3.py")
        else:
            print("Please choose only above options")
    except KeyboardInterrupt:
        os.system("cls")
        for i in range(3, 0, -1):
            print(f"Animation Terminating in {i}s", end="\r", flush=True)
            time.sleep(1.0)