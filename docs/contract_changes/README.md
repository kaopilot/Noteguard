# Contract change requests

After CP0, anything under `noteguard/contracts/`, `fixtures/expected/declarations.py`,
`rulesets/` schemas, or the route/wire shapes changes only through `CCR-NN.md` here:

    # CCR-NN — <title>
    Raised by: <lane, session>   Date:
    What changes (files, fields, values):
    Why (the failing case or missing capability):
    Lanes affected and what each must do:
    Golden fixture impact (regenerate with `make goldens`; review sheet diff attached):
    Status: proposed | approved (integrator, date) | rejected (reason)

The integrator lands the contract change and the golden update in one commit. Never change a
contract to make your own test pass.
