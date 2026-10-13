# mistakes.md

My mistake log. Every row below was graded or named in a past session with my coach. All dates are 2026.

**How to use this file**
1. Before every Saturday test, read the fix rules first, then the log.
2. After every graded piece of work, add a new row at the bottom of the log.
3. When I get the same thing right later in a test or practice, change Retested to Y and add the date.

## Fix rules (read these before every test)
1. Copy names exactly from the task. Class names start with a capital letter (`Bot`, `Book`, `Cart`).
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

## Log
| Date | Where | Mistake | Why | Fix rule | Retested |
|---|---|---|---|---|---|
| 25 Sep | Day 0 · Q2 | Named the function `count_vowel`, not `count_vowels` | Didn't copy the name from the task | Copy names exactly from the spec | N |
| 25 Sep | Day 0 · Q3 | Didn't run `average([])` | Only tested the normal case | Test the normal case and the edge case every time | N |
| 25 Sep | Day 0 · Q2–Q3 | Wrote functions in the `>>>` shell | Habit | Functions go in `.py` files | Y (10 Oct) |
| 25 Sep | Warm-up · Q2 | Wrote `3.0, 0.0` for `print(m, total)` | Assumed `print` adds commas | `print(a, b)` separates values with a space | N |
| 25 Sep | Warm-up · Q1 | Computed the mean inside the loop | Didn't think about when the line runs | Totals inside the loop, final result after it | N |
| 25 Sep | Warm-up redo | Answered half of Q3, and used code when told to use pen and paper | Rushed; didn't re-read the question | Re-read the question and answer every part before sending | N |
| 26 Sep | `variance.py` | Sent it without the output and the "why we square" answer | Didn't check the task list before sending | Before sending, tick off every item the task asks for | N |
| 26 Sep | Loop lesson · Step 1 check (b) | Printed −2 for `range(7, 0, -3)` | Kept counting past the stop | `range` never crosses the stop; counting down, every number must be above it | Y |
| 2 Oct | `resume.py` · `choice()` | No `return`, so `t` was `None` and every option said "Not found" | A function without `return` gives back `None` | If I write `x = f()`, `f` must return something; `print(x)` to check | Y |
| 2 Oct | `resume.py` · line 57 | Wrote `edt`, but the variable was `Edt` → `NameError` | Python names are case-sensitive | Lowercase variable names only | Y |
| 2 Oct | `resume.py` · `main()` | Merged the two name questions and kept the one without `.title()` | Deleting duplicate code can delete the better copy | Before deleting a copy, check what each copy did | N |
| 6 Oct | P66 practice 2 | Used `zip()` on one book's attributes → `TypeError: 'int' object is not iterable` | Read `i.pages` as all the pages, but each loop pass gives one whole book | One object = one record: loop over the objects and read attributes with a dot | N |
| 6 Oct | P66 practice 1–2 | Named the classes `bot` and `book`, not `Bot` and `Book` | Repeat of Day 0 Q2: names not copied from the spec | Copy names exactly from the spec | N (repeated with `cart` on 10 Oct) |
| 6 Oct | P66 practice 1–2 | Used the `>>>` shell, not `p66_practice.py` | Repeat of the Day 0 habit | Code goes in `.py` files | Y (10 Oct) |
| 10 Oct | P67 practice · my Player | `self.online = self.online.append(player)` left every player's `online` as `None` | `append` returns `None`, and assigning through `self.` creates a new attribute on the object | Never assign the result of `.append()`; change a class attribute through the class name | N |
| 10 Oct | P67 practice · my cart | Appended the whole `*items` tuple as one item | `*items` packs all the arguments into one tuple | Loop over `*items` to add each one, and check with `len()` | N |
