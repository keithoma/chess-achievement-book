- stockfish
- leela
- maia

## PATTERNS

disagreement means a delta of 5% or more change in the win percentage

- all agreement => obvious move
- all high depth engines agree & all low depth engines misses => brilliant move
- sf & lc0 agree, but maia does not => computerish move
- lc0 & maia agree, but sf does not => this is improbable, but the interpretation must mean there is an insane combination that is hidden
- sf & maia agree, but lc0 does not => there is a deep positioal concept hidden in the position
- sf, lc0, and maia all disagree => this means the position is insanely complicated, we can actually use the level of these three disagreeing as an index for complexity

### PROBABLY IMPOSSIBLE COMBINATIONS

- a low depth engine agreeing with sf or lc0, but not with maia => this would mean overthinking: there was an obvious good looking move, maia computed it, saw a problem and disregarded it, but that move actually worked