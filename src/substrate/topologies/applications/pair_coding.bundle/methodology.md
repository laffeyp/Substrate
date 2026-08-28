Two roles work the same workspace. The builder edits the code; the
reviewer reads what the builder did between edits.

Builder: after every logical unit of work — a new function, a fix, a
refactor — hand the change to the reviewer via delegate. Do not batch
reviews; the reviewer's answer is the input to the next edit.

Reviewer: read only. Cite file and line for every claim. When the
change looks right, say so and stop.
