# estore-backend
# estore-backend
# estore-backend
# estore-backend
# estore-backend
# Local store environments

Store credentials live in ignored `.env.iplug` and `.env.oakandloom` files.
Run Django management commands through the store selector:

```sh
venv/bin/python manage_store.py iplug runserver
venv/bin/python manage_store.py oak runserver
```

The same selector works with other management commands, for example
`venv/bin/python manage_store.py oak migrate` or `createsuperuser`. Run one
API on port 8000 at a time, or provide a different port to `runserver` and
set the matching frontend API URL. Oak & Loom's payment and social credentials
must be configured separately before enabling those integrations.
