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

def ask(prompt, kind='Text', default=None):
    params = dict(WFAskActionPrompt=prompt, WFInputType=kind)
    if default is not None:
        params['WFAskActionDefaultAnswer'] = default
    return action('ask', **params)

def format_date(value, pattern):
    return action('format.date', WFDate=text(reference=value), WFDateFormatStyle='Custom',
                  WFDateFormat='Custom', WFDateFormatString=pattern, WFLocale='en_US_POSIX')

def variable(name):
    return {'Type': 'Variable', 'VariableName': name}

def pick(values, prompt):
    items = action('list', WFItems=values)
    return action('choosefromlist', WFInput=ref(items), WFChooseFromListActionPrompt=prompt,
                  WFChooseFromListActionSelectMultiple=False)

endpoint = action('gettext', WFTextActionText='https://your-hourleaf.example/api/entries/')
token = action('gettext', WFTextActionText='PASTE_YOUR_API_TOKEN')
action('comment', WFCommentActionText='Configure the two Text fields above with your complete entries API URL and token. Date and range times use native pickers. Duration uses hours/minutes lists. Do not share a configured copy containing your token.')
# URL fields require editor-visible token strings, not bare token attachments.
entry_url = action('url', WFURLActionURL=text(reference=endpoint))
types_text = action('replacetext', WFInput=text(reference=endpoint),
                    WFReplaceTextFind='/entries/?$', WFReplaceTextReplace='/work-types/',
                    WFReplaceTextRegularExpression=True, WFReplaceTextCaseSensitive=True)
types_url = action('url', WFURLActionURL=text(reference=types_text))
headers = fields({'Authorization': text('Token ', token),
                  'Content-Type': 'application/json', 'Accept': 'application/json'})
previous = action('downloadurl', WFURL=text(reference=types_url), WFHTTPMethod='GET', WFHTTPHeaders=headers)
new_label = '＋ Add a new work type'
initial = action('list', WFItems=[new_label])
action('setvariable', WFVariableName='Work types', WFInput=ref(initial))
repeat = str(uuid.uuid4()).upper()
action('repeat.each', GroupingIdentifier=repeat, WFControlFlowMode=0, WFInput=ref(previous))
name = action('getvalueforkey', WFInput=ref(variable('Repeat Item')),
              WFDictionaryKey='name', WFGetDictionaryValueType='Value')
action('appendvariable', WFVariableName='Work types', WFInput=ref(name))
action('repeat.each', GroupingIdentifier=repeat, WFControlFlowMode=2)
selected = action('choosefromlist', WFInput=ref(variable('Work types')),
                  WFChooseFromListActionPrompt='Choose a previous work type or add a new one',
                  WFChooseFromListActionSelectMultiple=False)
condition = str(uuid.uuid4()).upper()
action('conditional', GroupingIdentifier=condition, WFControlFlowMode=0,
       WFInput={'Type': 'Variable', 'Variable': ref(selected)},
       WFCondition=4, WFConditionalActionString=new_label)
new_name = ask('New work type')
action('setvariable', WFVariableName='Selected work type', WFInput=ref(new_name))
action('conditional', GroupingIdentifier=condition, WFControlFlowMode=1)
action('setvariable', WFVariableName='Selected work type', WFInput=ref(selected))
action('conditional', GroupingIdentifier=condition, WFControlFlowMode=2)
work_type = variable('Selected work type')
now = action('date', WFDateActionMode='Current Date')
chosen_date = ask('Work date', 'Date', text(reference=now))
day = format_date(chosen_date, 'yyyy-MM-dd')
group = str(uuid.uuid4()).upper()
choices = ['Total duration', 'Start/end range']
action('choosefrommenu', GroupingIdentifier=group, WFControlFlowMode=0,
       WFMenuPrompt='How would you like to enter your work?', WFMenuItems=choices)
for choice in choices:
    action('choosefrommenu', GroupingIdentifier=group, WFControlFlowMode=1, WFMenuItemTitle=choice)
    body = {'date': text(reference=day), 'work_type': text(reference=work_type)}
    if choice == choices[0]:
        hours = pick([f'{n:02}' for n in range(25)], 'Hours worked')
        minutes = pick([f'{n:02}' for n in range(60)], 'Additional minutes (choose 00 for 24 hours)')
        duration_text = text(reference=hours)
        duration_text['Value']['string'] += ':\ufffc'
        duration_text['Value']['attachmentsByRange']['{2, 1}'] = minutes
        duration = action('gettext', WFTextActionText=duration_text)
        body['duration'] = text(reference=duration)
    else:
        start = format_date(ask('Start time', 'Time', text(reference=now)), 'HH:mm')
        end = format_date(ask('End time (later on the same date)', 'Time', text(reference=now)), 'HH:mm')
        body.update(start_time=text(reference=start), end_time=text(reference=end))
    response = action('downloadurl', WFURL=text(reference=entry_url), WFHTTPMethod='POST',
                      WFHTTPBodyType='JSON', WFJSONValues=fields(body), WFHTTPHeaders=headers)
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
requests = [a['WFWorkflowActionParameters'] for a in ACTIONS if a['WFWorkflowActionIdentifier'].endswith('.downloadurl') and a['WFWorkflowActionParameters']['WFHTTPMethod'] == 'POST']
assert len(requests) == 2
for request, expected in zip(requests, [{'date', 'work_type', 'duration'}, {'date', 'work_type', 'start_time', 'end_time'}]):
    assert {v['WFKey']['Value']['string'] for v in request['WFJSONValues']['Value']['WFDictionaryFieldValueItems']} == expected
# Regression checks for fields that previously imported as blank or text-only.
all_requests = [a['WFWorkflowActionParameters'] for a in ACTIONS
                if a['WFWorkflowActionIdentifier'].endswith('.downloadurl')]
assert [r['WFHTTPMethod'] for r in all_requests] == ['GET', 'POST', 'POST']
for request in all_requests:
    assert request['WFURL']['WFSerializationType'] == 'WFTextTokenString'
    assert request['WFURL']['Value']['attachmentsByRange']
inputs = [a['WFWorkflowActionParameters']['WFInputType'] for a in ACTIONS
          if a['WFWorkflowActionIdentifier'].endswith('.ask')]
assert inputs == ['Text', 'Date', 'Time', 'Time']
assert duration_text['Value']['string'] == '\ufffc:\ufffc'
assert set(duration_text['Value']['attachmentsByRange']) == {'{0, 1}', '{2, 1}'}
path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
with path.open('wb') as stream:
    plistlib.dump(workflow, stream, sort_keys=False)
print(f'Wrote {len(ACTIONS)} actions to {path}')
