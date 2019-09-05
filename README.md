## Placebo

Placebo is Control Group's quartermaster tool for the [MIT Mystery Hunt]. In
combination with Slack, Google Sheets, and a hot water dispenser to make tea, it
helps us keep track of puzzles as they unlock, and organize who's working on
what.

### Installation

We're actively using it on Control Group, but the installation flow hasn't
really been polished. Instructions to follow soon for anyone who wants to try
anyway.

### Usage

* **For solvers:** This is a tool the quartermasters (QMs) are using. You don't
  have to do anything with it!

  * For our list of all the puzzles, and links to the spreadsheet and Slack
    channel for working on each of them, see the [Puzzle List spreadsheet] (2019
    link).
  
  * If you're interested in updates when new puzzles are unlocked, keep an eye
    on the #unlocks channel in Slack.

* **For QMs:** You can use these commands from any Slack channel. (If you're not
  QMing, please don't! We can easily become flustered and confused. Come chat
  with us! We're at a table up front or in the #qm channel on Slack.)

  * When a new round is unlocked:
    `/newround Round Name https://example.com/round`
    
  * When a new puzzle is unlocked:
    `/unlock Puzzle Name https://example.com/puzzle Round Name`
    
  * After you get a phone call from HQ telling you an answer was correct:
    `/correct Puzzle Name PUZZLE SOLUTION`
    
  All those commands will update the Puzzle List spreadsheet, as well as
  individual puzzles' working spreadsheets and Slack channels. If anything weird
  happens (say, because the Hunt isn't structured in the way we expected) you
  can fix it by hand afterward -- that won't interfere with the tool.
  
[MIT Mystery Hunt]: https://www.mit.edu/~puzzle/
[Puzzle List spreadsheet]: https://docs.google.com/spreadsheets/d/1FctlfZu7ECWEqWCHDNm7AD8iT_ucik7Cv9PB1aRPFR8/edit#gid=287461192