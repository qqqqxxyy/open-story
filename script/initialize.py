"""Materialize private, per-installation creative defaults from a public template."""
from pathlib import Path
import argparse
import json
import os
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- openstory-local-defaults:start -->'
END = '<!-- openstory-local-defaults:end -->'


def read_preferences(root=ROOT):
    path = Path(root)/'.openstory/preferences.json'
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return None


def status(root=ROOT):
    root = Path(root)
    profile = read_preferences(root)
    contract = root/'author/writing-contract.md'
    return {'initialized': profile is not None and contract.is_file(),
            'needs_preferences': profile is None,
            'needs_contract': not contract.is_file(),
            'contract_path': str(contract)}


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=path.parent,
                                     prefix='.initialize-', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def defaults_block(profile):
    sections = [START, '以下为本次安装由使用者选择的创作默认值；具体故事中的明确要求优先。']
    for key, label in [('protagonist', '默认主人公'), ('narration', '默认叙述视角')]:
        value = profile[key]
        sections.extend(['', '### '+label])
        if value is None:
            sections.append('不设固定默认，按每个故事的讨论结果确定。')
        else:
            sections.append('```json\n'+json.dumps(value, ensure_ascii=False, indent=2)+'\n```')
    sections.extend(['', END])
    return '\n'.join(sections)


def initialize(root, profile):
    root = Path(root)
    for key in ('protagonist', 'narration'):
        if key not in profile or (profile[key] is not None and not isinstance(profile[key], dict)):
            raise ValueError(key+' must be an object or null; ask the user before initialization')
    template = (root/'author/writing-contract.template.md').read_text(encoding='utf8')
    if template.count('{{LOCAL_DEFAULTS}}') != 1:
        raise ValueError('Writing contract template requires exactly one defaults placeholder')
    target = root/'author/writing-contract.md'
    block = defaults_block(profile)
    if target.exists():
        existing = target.read_text(encoding='utf8')
        pattern = re.compile(re.escape(START)+r'[\s\S]*?'+re.escape(END))
        if len(pattern.findall(existing)) != 1:
            raise ValueError('Existing local contract has no unique managed defaults section; preserve it and resolve explicitly')
        contract = pattern.sub(lambda match: block, existing)
    else:
        contract = template.replace('{{LOCAL_DEFAULTS}}', block)
    preferences = root/'.openstory/preferences.json'
    serialized = json.dumps(profile, ensure_ascii=False, indent=2)+'\n'
    if not preferences.exists() or preferences.read_text(encoding='utf8') != serialized:
        atomic_write(preferences, serialized)
    if not target.exists() or target.read_text(encoding='utf8') != contract:
        atomic_write(target, contract)
    return status(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--status', action='store_true', help='Report whether this installation has user-selected defaults')
    actions.add_argument('--content-file', type=Path, help='UTF-8 JSON with protagonist and narration objects or null')
    actions.add_argument('--restore', action='store_true', help='Restore a missing local contract from saved preferences')
    parser.add_argument('--root', type=Path, default=ROOT, help='Skill installation root; defaults to this script installation')
    args = parser.parse_args(argv)
    try:
        if args.status:
            result = status(args.root)
        else:
            profile = (json.loads(args.content_file.read_text(encoding='utf-8-sig'))
                       if args.content_file else read_preferences(args.root))
            if profile is None:
                raise ValueError('No saved preferences; ask the user about protagonist and narration first')
            result = initialize(args.root, profile)
        print(json.dumps({'ok': True, **result}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
