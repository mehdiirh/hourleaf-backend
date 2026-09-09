# Log work to Hourleaf — Apple Shortcut

Open `Hourleaf.shortcut` on your iPhone and add it to Shortcuts. During setup enter:

1. Your complete entries endpoint, for example `https://hours.example.com/api/entries/`.
2. Your API token, without the `Token ` prefix.

If setup questions do not appear, edit the shortcut and replace its first two Text actions. An administrator can get a token by running this from the backend directory:

```sh
docker compose exec backend python manage.py api_token YOUR_USERNAME
```

Run the shortcut, confirm today's Gregorian date (YYYY-MM-DD), enter a work type, and choose:

- **Total duration:** hours and minutes, such as `02:30` (00:01 through 24:00).
- **Start/end range:** 24-hour times, such as `09:00` and `11:30`. The end must be later on the same date; split overnight work across dates.

The shortcut submits one JSON request and shows the API response. A response containing the new entry's `id` confirms creation. Validation errors appear in the response; network or HTTP errors may be displayed by Shortcuts itself. It does not retry automatically. If a connection fails after submitting, check Hourleaf before running again to avoid duplicate entries.

Use the same work type spelling as in Hourleaf. This shortcut uses free-text work types; it does not fetch suggestions.

Your iPhone must be able to reach the server. `localhost` on an iPhone refers to the phone itself. For LAN access, see the main README's `APP_BIND`, allowed-host and port settings. Use your HTTPS server URL for access over a network. A saved token is editable inside the shortcut: share only the unconfigured template.

To add an icon, open the shortcut's details/menu in Shortcuts and choose **Add to Home Screen**.

## Rebuild on macOS

Requires Python 3 and Apple's Shortcuts command-line tool:

```sh
python3 integrations/apple-shortcuts/build.py /tmp/Hourleaf.unsigned.shortcut
shortcuts sign --mode anyone --input /tmp/Hourleaf.unsigned.shortcut --output /tmp/Hourleaf.shortcut
```

The generator checks action references and both mutually exclusive API payloads. Apple signing was verified. Interactive execution on a physical iPhone has not been tested; no live records were created during development.
