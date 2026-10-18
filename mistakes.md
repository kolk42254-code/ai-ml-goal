# mistakes.md

My mistake log. Every row below was graded or named in a past session with my coach. All dates are 2026.

**How to use this file**
1. Before every Saturday test, read the fix rules first, then the log.
2. After every graded piece of work, add a new row at the bottom of the log.
3. When I get the same thing right later in a test or practice, change Retested to Y and add the date.

## Fix rules (read these before every test)
1. Copy names exactly from the task. Class names start with a capital letter and capitalise every word (`Bot`, `Book`, `BankAccount`, `TodoList`).
2. Test the normal case and the edge case (like an empty list) every time.
3. Code goes in `.py` files, not the `>>>` shell.
4. `print(a, b)` separates values with a space, not a comma.
5. Running totals go inside the loop. The final result (like the mean) goes after it.
6. Re-read the question and answer every part before sending. Tick off every item the task asks for.
7. `range` never crosses the stop value. Counting down, every number must stay above it.
8. A function without `return` gives back `None`. If I write `x = f()`, `f` must return something.
9. Python names are case-sensitive: `edt` and `Edt` are different. Use lowercase variable names.
10. Before deleting a copy of some code, check what each copy did.
11. One object = one record: loop over the objects and read their attributes with a dot. No `zip`.
12. Never assign the result of `.append()`, because it returns `None`. To change a class attribute, go through the class name: `Player.online.append(player)`.
13. `*items` packs all the arguments into one tuple. Loop over it to add each item.
14. Check both ends of an amount or size: block 0, negatives and too-big values (like more values than an array holds). Test 0, a negative and a too-big value.
15. One list holds one kind of item. Each history entry says what happened: `"Deposited 1000"`, not `1000`.
16. After a fix, run the file and check each output line against what really happened.
17. `+` joins strings with nothing in between. Put the space inside the quotes: `"Deposit " + str(amount)`.
18. Read every printed message for spelling before committing.
19. Write `return` only to send back a value or to stop early. A `return` on the last line of a function does nothing.
20. One blank line between methods.
21. File names are lowercase with underscores and no spaces: `p68_practice.py`.
22. A commit message says what changed and matches what's in the commit: `P68: fix history text`, not `p68` or `todo.py`.
23. Before running a copied command, replace its placeholder text (`Your Name`, `your-key-here`) with my real values.
24. An edge-case branch prints something I can see (`No tasks yet`), so the output proves the test ran.
25. Check dunder names: 2 underscores on each side (`__init__`, `__str__`).
26. The last step of the std is the square root: `std = variance ** 0.5`.
27. Whole group: divide by n. Sample: divide by n − 1, which needs at least 2 values.
28. Return numbers, not text: `0`, not `"0"`.

## Log
| Date | Where | Mistake | Why | Fix rule | Retested |
|---|---|---|---|---|---|
| 25 Sep | Day 0 · Q2 | Named the function `count_vowel`, not `count_vowels` | Didn't copy the name from the task | Copy names exactly from the spec | N |
| 25 Sep | Day 0 · Q3 | Didn't run `average([])` | Only tested the normal case | Test the normal case and the edge case every time | Y (13 Oct, `todo.py`: tested an empty list unprompted) |
| 25 Sep | Day 0 · Q2–Q3 | Wrote functions in the `>>>` shell | Habit | Functions go in `.py` files | Y (10 Oct) |
| 25 Sep | Warm-up · Q2 | Wrote `3.0, 0.0` for `print(m, total)` | Assumed `print` adds commas | `print(a, b)` separates values with a space | N |
| 25 Sep | Warm-up · Q1 | Computed the mean inside the loop | Didn't think about when the line runs | Totals inside the loop, final result after it | Y (18 Oct, `stat.c`: total inside the loop, mean after it) |
| 25 Sep | Warm-up redo | Answered half of Q3, and used code when told to use pen and paper | Rushed; didn't re-read the question | Re-read the question and answer every part before sending | N |
| 26 Sep | `variance.py` | Sent it without the output and the "why we square" answer | Didn't check the task list before sending | Before sending, tick off every item the task asks for | N |
| 26 Sep | Loop lesson · Step 1 check (b) | Printed −2 for `range(7, 0, -3)` | Kept counting past the stop | `range` never crosses the stop; counting down, every number must be above it | Y |
| 2 Oct | `resume.py` · `choice()` | No `return`, so `t` was `None` and every option said "Not found" | A function without `return` gives back `None` | If I write `x = f()`, `f` must return something; `print(x)` to check | Y |
| 2 Oct | `resume.py` · line 57 | Wrote `edt`, but the variable was `Edt` → `NameError` | Python names are case-sensitive | Lowercase variable names only | Y |
| 2 Oct | `resume.py` · `main()` | Merged the two name questions and kept the one without `.title()` | Deleting duplicate code can delete the better copy | Before deleting a copy, check what each copy did | N |
| 6 Oct | P66 practice 2 | Used `zip()` on one book's attributes → `TypeError: 'int' object is not iterable` | Read `i.pages` as all the pages, but each loop pass gives one whole book | One object = one record: loop over the objects and read attributes with a dot | N |
| 6 Oct | P66 practice 1–2 | Named the classes `bot` and `book`, not `Bot` and `Book` | Repeat of Day 0 Q2: names not copied from the spec | Copy names exactly from the spec | Y (13 Oct); repeated with `cart` on 10 Oct |
| 6 Oct | P66 practice 1–2 | Used the `>>>` shell, not `p66_practice.py` | Repeat of the Day 0 habit | Code goes in `.py` files | Y (10 Oct) |
| 10 Oct | P67 practice · my Player | `self.online = self.online.append(player)` left every player's `online` as `None` | `append` returns `None`, and assigning through `self.` creates a new attribute on the object | Never assign the result of `.append()`; change a class attribute through the class name | N |
| 10 Oct | P67 practice · my cart | Appended the whole `*items` tuple as one item | `*items` packs all the arguments into one tuple | Loop over `*items` to add each one, and check with `len()` | N |
| 13 Oct | P68 practice · `withdraw` | No check for 0 or negative amounts, so `withdraw(-500)` added 500 to the balance | `-500 > 1000` is `False`, so the only check passed, and `balance -= -500` adds 500 | Check both ends of an amount: block 0 and negatives, not only "too much" | N |
| 13 Oct | P68 practice · `history` | Saved deposits as bare numbers (`1000`) and withdrawals as sentences | A bare number doesn't say if money came in or went out, and mixed types make the list hard to use later | One list holds one kind of item; each history entry says what happened | N |
| 13 Oct | P68 practice · `Bankaccount` | Tested only `deposit(1000)` and `withdraw(500)`: no 0, negative or too-big amounts | Repeat of 25 Sep Day 0 Q3 (but `best_lap()` on an empty bot was tested this time) | Test the normal case and the edge case every time | N |
| 13 Oct | P68 fix 1 · `withdraw` | Put the deposit history line inside `withdraw`, so every withdrawal was also saved as a deposit (`deopsit 500`) | A line runs in the method it sits in, so the deposit line ran on every withdrawal | After a fix, run the file and check each output line against what really happened | N |
| 13 Oct | P68 fix 2 · `deposit` | `"Deposit" + str(amount)` printed `Deposit1000`, with no space | `+` joins strings exactly as they are and never adds a space (`print(a, b)` does) | Put the space inside the quotes: `"Deposit " + str(amount)` | N |
| 13 Oct | P68 fix 2 | Did 2 of the 3 fix steps: no `withdraw(0)` or `withdraw(-500)` test, but the commit message says "test withdraw" | Repeat of 26 Sep `variance.py`: didn't tick off the task list before sending | Tick off every item the task asks for before committing; the commit message must match what's in the file | N |
| 13 Oct | P68 practice · messages | Typos in printed text: `greater then 10`, `Withdrawnn amount` | Printed text is part of the output; both typos are still in the file | Read every printed message for spelling before committing (rule 18) | N |
| 13 Oct | P68 practice · `deposit` | Wrote a `return` at the end of both the `if` branch and the `else` branch | The method ends there anyway, so both `return`s do nothing | Write `return` only to send back a value or to stop early (rule 19) | N |
| 13 Oct | P68 practice · layout | No blank line between `deposit`, `withdraw` and `show` | The methods run into each other, so it's hard to see where one ends | One blank line between methods (rule 20) | N |
| 13 Oct | P68 practice · file name | Named the file `P68 practice.py`, with a space | The `import` statement can't name a file with a space (needed from P78), and every terminal command needs quotes | Lowercase with underscores: `p68_practice.py` (rule 21) | N |
| 13 Oct | P68 practice · `Bankaccount` | Named the class `Bankaccount`, not `BankAccount` | Class names capitalise every word, not only the first | Capitalise every word in a class name (rule 1) | N |
| 13 Oct | P68 · commits | Commit messages `p68` and `mistakes log and P68 files`, but the P68 file wasn't in the second commit | A commit message is the record of what changed; one says nothing, and the other names a file that isn't in it | The message says what changed and matches the commit (rule 22) | N |
| 13 Oct | Git setup | Git name and email were tutorial placeholders: `Your Name` and `the email of your GitHub account` | Placeholder text was run as if it were real, so GitHub couldn't link my first 2 commits to my account | Replace placeholder text before running a copied command (rule 23) | N |
| 13 Oct | `todo.py` · commit | Commit message `todo.py` is only the file name | Repeat of the `p68` commit message from earlier the same day | The message says what changed: `Add TodoList with add, done and show` (rule 22) | N |
| 13 Oct | `todo.py` · `show()` | The empty-list check does `return None`, so `e.show()` prints nothing | Without the check, the empty loop also prints nothing and `show` also returns `None`, so the check changes nothing and the output can't show the test ran | An edge-case branch prints something I can see: `No tasks yet` (rule 24) | N |
| 13 Oct | `todo.py` · layout | No blank line between `__init__`, `add` and `done` | Repeat of P68 from the same day | One blank line between methods (rule 20) | N |
| 13 Oct | C lab · commits | `removed c1.c` was really a rename to `dublicate.c`; `area and volume of circle` computes a sphere (a circle has no volume) | Repeat of the P68 and `todo.py` commits: the message doesn't match the commit | The message says what changed and matches the commit (rule 22) | N |
| 13 Oct | C lab · `dublicate.c` | The arrays hold 50 numbers, but `n` is never checked: entering 60 numbers crashed with a segmentation fault | Numbers 51–60 are written past the end of the arrays, into memory they don't own | Check both ends of an amount: stop if `n` is below 1 or above 50 (rule 14) | N |
| 13 Oct | C lab · `area.c` | No check on the radius: `r = -2` printed a volume of `-33.493332` | `r*r` hides the minus sign, so the area looks fine, but `r*r*r` keeps it, so the volume goes negative | Check both ends of an amount: reject a negative radius; test 0 and a negative (rule 14) | N |
| 16 Oct | Diamond practice | Wrote `def __init(self)`, so `Base` never printed | Python only runs `__init__` automatically, with `__` on both sides | Check dunder names: 2 underscores on each side (rule 25) | N |
| 17 Oct | M6 practice · `std()` | Returned the variance (`12.0`), with no square root | Stopped one step before the end of the formula | The last step of the std is the square root (rule 26) | N |
| 17 Oct | M6 practice · `std()` | Divided by `len(marks)-1`, so `std([7])` crashed with `ZeroDivisionError` | Mixed up M6 (divide by n) with M7 (divide by n − 1), and never tested a one-value list | Whole group: n. Sample: n − 1, with at least 2 values. Always test one value (rules 2, 27) | N |
| 17 Oct | M6 practice · `std()` | Returned `"0"` for an empty list, so `std([]) * 2` gave `00` | Quotes make it text, and text × 2 repeats it | Return numbers, not text (rule 28) | N |
| 17 Oct | M6 practice · `std()` | Wrote the function in the `>>>` shell | Repeat of 25 Sep and 6 Oct, after both were marked fixed on 10 Oct | Code goes in `.py` files (rule 3) | N |
| 18 Oct | M7 in C · `stat.c` | One value printed `-nan` | Dividing a double by 0 in C gives `nan`, with no error | Check `len < 2` before dividing by n − 1; test one value (rules 14, 27) | N |
| 18 Oct | M7 in C · `stat.c` | 25 values overflowed `data[20]`: `*** stack smashing detected ***` | Repeat of 13 Oct `dublicate.c`: C doesn't check array limits | Check the size against the array length: 2 to 20 here (rule 14) | N |
| 18 Oct | M7 in C · `stat.c` | Printed text says `varience` | Repeat of the 13 Oct typos in printed messages | Read every printed message for spelling (rule 18) | N |
