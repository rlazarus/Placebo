## Design principles

1. Few assumptions about the Hunt -- we won't know much it about in advance.
   1. There are puzzles.
   1. Every puzzle has a word-or-short-phrase solution.
   1. Every puzzle has a unique name.
   1. Puzzles are probably divided into rounds, but that may be a little wonky
      (e.g. in 2018 some puzzles belonged to more than one round).
   1. Every round probably has a metapuzzle.
1. Easy to stop using.
   1. If the tool does the wrong thing, we should be able to correct it easily.
   1. If the tool doesn't work, e.g. because an assumption is wrong, we should
      be able to immediately go back to doing things by hand without losing
      anything.
   1. If any individual QM doesn't want to use the tool, they should be able to
      do QM stuff by hand without the tool getting in their way or them getting
      in the tool's (as long as it's not the same puzzle at the same time).
1. No actions that can't be undone.
   1. Sometimes deleting a row or a sheet is the right thing, but those cases
      are unusual and we'll do them by hand.
1. The tool doesn't need to be secret or pretend to be human, but it should be
   polite.
1. Nobody should have to care about it except the QMs.
   1. Solvers shouldn't need to learn how to interact with the tool -- it
      should conform to them, not the other way around.


## Design decisions

* No or minimal data schema. We won't try to model the Hunt. [1]
* No data store except the human-readable and -editable Google Sheet. [1, 2]
* Every action is manually triggered -- we won't try to monitor the Hunt site
  for changes. (If we feel really clever we might change this to "manually
  confirmed" but that's as far as we go.) [2]
* No automated deletion or destruction of anything, either when a puzzle is
  solved or when it was added by accident. Reversible archiving is okay. [3]
* Automated messages are allowed but should never be annoying or spammy. [4, 5]
* We won't integrate at all with the content of the spreadsheets used to solve
  puzzles. [5]
* No tool-assisted state updates before a puzzle is solved (like from "Working"
  to "Stuck-E") -- solvers or QMs will update the tracking sheet directly. [5]
* No change to the "I have an answer, call it in" workflow; QMs just use the
  tool to update state after they get the phone call confirming the answer was
  correct. [5]


## Functions

* Add round
  * Create meta doc
  * Create meta channel
  * Set topic in meta channel
  * Add meta to tracking sheet
  * Announce in #unlocks
* Add puzzle
  * Create doc
  * Create channel
  * Set topic in channel
  * Add to tracking sheet
  * Announce in #unlocks
  * Acknowledge in #qm
* Mark puzzle solved
  * Add "[SOLVED]" to doc name
  * Move doc to Solved folder
  * Update tracking sheet status
  * Update tracking sheet solution
  * Send message to channel
  * Archive channel
  * Acknowledge in #qm
* Mark puzzle backsolved
  * Add "[BACKSOLVED]" to doc name
  * Update tracking sheet status
  * Update tracking sheet solution
  * Send message to channel
  * Acknowledge in #qm
