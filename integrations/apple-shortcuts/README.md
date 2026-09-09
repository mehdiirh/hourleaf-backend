# Log work to Hourleaf — Apple Shortcut

Open `Hourleaf-v3.shortcut` on your iPhone and add it to Shortcuts. During setup enter:

1. Your complete entries endpoint, for example `https://hours.example.com/api/entries/`.
2. Your API token, without the `Token ` prefix.

If setup questions do not appear, edit the shortcut and replace its first two Text actions. An administrator can get a token by running this from the backend directory:

```sh
docker compose exec backend python manage.py api_token YOUR_USERNAME
```

Run the shortcut. It fetches your saved work types and displays them in a list, with **Add a new work type** available even when you have no history. Select a type, then choose the work date using the native date picker (default today). Dates are formatted for the API automatically.

Choose how to record the time:

- **Total duration:** select hours and minutes from two lists. The total must be 00:01 through 24:00.
- **Start/end range:** choose both times using native time pickers. The end must be later on the same date; split overnight work across dates.

The shortcut submits one JSON request and shows the API response. A response containing the new entry's `id` confirms creation. Validation errors appear in the response; network or HTTP errors may be displayed by Shortcuts itself. It does not retry automatically. If a connection fails after submitting, check Hourleaf before running again to avoid duplicate entries.

Existing types are fetched from `/api/work-types/` using your token. Only a newly added type requires typing. Keep the configured entries URL ending in `/api/entries/`; the work-types URL is derived from it.

Your iPhone must be able to reach the server. `localhost` on an iPhone refers to the phone itself. For LAN access, see the main README's `APP_BIND`, allowed-host and port settings. Use your HTTPS server URL for access over a network. A saved token is editable inside the shortcut: share only the unconfigured template.

To add an icon, open the shortcut's details/menu in Shortcuts and choose **Add to Home Screen**.

## Rebuild on macOS

Requires Python 3 and Apple's Shortcuts command-line tool:

```sh
python3 integrations/apple-shortcuts/build.py /tmp/Hourleaf.unsigned.shortcut
shortcuts sign --mode anyone --input /tmp/Hourleaf.unsigned.shortcut --output /tmp/Hourleaf.shortcut
```

The generator checks action references, editor-visible request URL bindings, GET/POST methods, native picker types, duration formatting, and both mutually exclusive API payloads. Apple signing was verified. Interactive execution on a physical iPhone has not been tested; no live records were created during development.

## Version 2

Replaces bare request URL attachments with visible token strings wired through explicit URL actions; adds native date/time pickers, duration lists, and authenticated work-type retrieval. Replace the previous shortcut with this version and re-enter your URL and token.

## Version 3

Corrects the Replace Text identifier to `is.workflow.actions.text.replace`. All action identifiers were checked against the ToolKit v63 catalog and the separately documented control-flow actions. This fixes the Unknown Action immediately after the first URL action. Physical iPhone execution is still unverified.
