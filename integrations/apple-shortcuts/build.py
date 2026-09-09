#!/usr/bin/env python3
"""Generate Hourleaf's credential-free Apple Shortcut using only Python stdlib.

Usage: python3 build.py /path/to/Hourleaf.unsigned.shortcut
Then: shortcuts sign --mode anyone --input ... --output Hourleaf.shortcut
"""
import plistlib
import sys
import uuid
from pathlib import Path

ACTIONS = []

def action(kind, **params):
    uid = str(uuid.uuid4()).upper()
    ACTIONS.append({'WFWorkflowActionIdentifier': 'is.workflow.actions.' + kind,
                    'WFWorkflowActionParameters': {'UUID': uid, **params}})
    return {'Type': 'ActionOutput', 'OutputUUID': uid, 'OutputName': 'Result'}

def text(value='', reference=None):
    data = {'string': value}
    if reference:
        data['attachmentsByRange'] = {'{%d, 1}' % len(value): reference}
        data['string'] += '\ufffc'
    return {'Value': data, 'WFSerializationType': 'WFTextTokenString'}

def ref(value):
    return {'Value': value, 'WFSerializationType': 'WFTextTokenAttachment'}

def fields(values):
    return {'Value': {'WFDictionaryFieldValueItems': [
        {'WFItemType': 0, 'WFKey': text(key),
         'WFValue': value if isinstance(value, dict) else text(value)}
        for key, value in values.items()]}, 'WFSerializationType': 'WFDictionaryFieldValue'}

def ask(prompt, default=''):
    return action('ask', WFAskActionPrompt=prompt, WFInputType='Text',
                  WFAskActionDefaultAnswer=default, WFAskActionAllowsMultiline=False)

endpoint = action('gettext', WFTextActionText='https://your-hourleaf.example/api/entries/')
token = action('gettext', WFTextActionText='PASTE_YOUR_API_TOKEN')
action('comment', WFCommentActionText='Configure the two Text fields above with your complete entries API URL and token. Do not share a configured copy containing your token. Dates use Gregorian YYYY-MM-DD. Ranges must end later on the same date.')
now = action('date', WFDateActionMode='Current Date')
today = action('format.date', WFDate=text(reference=now), WFDateFormatStyle='Custom',
               WFDateFormat='Custom', WFDateFormatString='yyyy-MM-dd', WFLocale='en_US_POSIX')
day = ask('Date (Gregorian YYYY-MM-DD)', text(reference=today))
work_type = ask('Work type (use your usual name, e.g. Development)')
group = str(uuid.uuid4()).upper()
choices = ['Total duration (HH:MM)', 'Start/end range']
action('choosefrommenu', GroupingIdentifier=group, WFControlFlowMode=0,
       WFMenuPrompt='How would you like to enter your work?', WFMenuItems=choices)
for choice in choices:
    action('choosefrommenu', GroupingIdentifier=group, WFControlFlowMode=1, WFMenuItemTitle=choice)
    body = {'date': text(reference=day), 'work_type': text(reference=work_type)}
    if choice == choices[0]:
        duration = ask('Hours worked (HH:MM, from 00:01 to 24:00)', '01:00')
        body['duration'] = text(reference=duration)
    else:
        start = ask('Start time (24-hour HH:MM)', '09:00')
        end = ask('End time (24-hour HH:MM, later on the same date)', '17:00')
        body.update(start_time=text(reference=start), end_time=text(reference=end))
    response = action('downloadurl', WFURL=ref(endpoint), WFHTTPMethod='POST',
                      WFHTTPBodyType='JSON', WFJSONValues=fields(body),
                      WFHTTPHeaders=fields({'Authorization': text('Token ', token),
                                            'Content-Type': 'application/json', 'Accept': 'application/json'}))
    action('showresult', Text=text('Hourleaf response (an id confirms the saved entry):\n', response))
action('choosefrommenu', GroupingIdentifier=group, WFControlFlowMode=2)
workflow = {
    'WFWorkflowName': 'Log work to Hourleaf', 'WFWorkflowActions': ACTIONS,
    'WFWorkflowClientVersion': '3036.0.4',
    'WFWorkflowMinimumClientVersion': 900,
    'WFWorkflowMinimumClientVersionString': '900',
    'WFWorkflowIcon': {'WFWorkflowIconStartColor': 4292093695, 'WFWorkflowIconGlyphNumber': 61461},
    'WFWorkflowTypes': [], 'WFWorkflowInputContentItemClasses': [],
    'WFWorkflowOutputContentItemClasses': [],
    'WFWorkflowImportQuestions': [
        {'ActionIndex': index, 'Category': 'Parameter', 'ParameterKey': 'WFTextActionText',
         'Text': prompt, 'DefaultValue': ACTIONS[index]['WFWorkflowActionParameters']['WFTextActionText']}
        for index, prompt in [(0, 'Your full Hourleaf entries URL (ending in /api/entries/). Use a hostname or IP reachable from your iPhone.'),
                              (1, 'Your Hourleaf API token (paste the token only, without the Token prefix).')]
    ],
}
# Check references, the two exclusive payload shapes, and menu balance before export.
known = set()
for item in ACTIONS:
    params = item['WFWorkflowActionParameters']
    def check(value):
        if isinstance(value, dict):
            if value.get('Type') == 'ActionOutput':
                assert value['OutputUUID'] in known, 'Forward or missing action reference'
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(params)
    known.add(params['UUID'])
requests = [a['WFWorkflowActionParameters'] for a in ACTIONS if a['WFWorkflowActionIdentifier'].endswith('.downloadurl')]
assert len(requests) == 2
for request, expected in zip(requests, [{'date', 'work_type', 'duration'}, {'date', 'work_type', 'start_time', 'end_time'}]):
    assert {v['WFKey']['Value']['string'] for v in request['WFJSONValues']['Value']['WFDictionaryFieldValueItems']} == expected
path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
with path.open('wb') as stream:
    plistlib.dump(workflow, stream, sort_keys=False)
print(f'Wrote {len(ACTIONS)} actions to {path}')
