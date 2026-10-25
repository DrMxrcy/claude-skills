# Users

Look a user up with `get_user(user_id)`; it returns `None` when the id is unknown.
`views.profile` and `report.names` both call `get_user`.
