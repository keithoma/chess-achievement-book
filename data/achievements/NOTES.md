# Notes

## Shelves Achievements

### Badges

- games won by method (checkmate, timeout, abandonment, resignation)
- win a game longer than 80 moves

these five are shelved for now because they promote toxic play patterns and furthermore the player 
is not in control to get them

instead:
- make win a long game into a hidden feat with stalling detection logic
- make timeout win to win a time scramble
- make resignation into a hidden feat where opponent resigns in a completely winning position "Huh?"
- we already have a checkmate book in feats

---

This is fundamentally a different kind of achievement, streak badges? Idk

###############################################################################
# SECTION 5: WIN STREAKS
###############################################################################
- id: badge_win_streak
  type: badge
  category: Win Streaks
  name: Winning Streak
  description: win three games in a row
  config:
    tiers:
      bronze: 10
      silver: 50
      gold: 250