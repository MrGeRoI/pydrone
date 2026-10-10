"""UTF-8 translation catalogs with English fallback and format templates."""
import json
import re
from pathlib import Path
from string import Formatter
from .config import DATA

LOCALE_PATH=DATA.parent/'locale'

class Locale:
    def __init__(self,language='english',root=LOCALE_PATH):
        self.root=Path(root)
        self.english=self._read('english');self.language='english';self.strings=dict(self.english)
        self.select(language)

    def _read(self,language):
        if not isinstance(language,str) or not re.fullmatch(r'[a-z][a-z0-9_-]*',language):raise ValueError('Invalid language name')
        data=json.loads((self.root/f'{language}.json').read_text(encoding='utf8'))
        if not isinstance(data,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in data.items()):raise ValueError('Locale must contain string keys and values')
        return data

    @staticmethod
    def fields(value):return [field for _,field,_,_ in Formatter().parse(value) if field is not None]

    def select(self,language):
        translated=self._read(language)
        for key,value in translated.items():
            if key in self.english and sorted(self.fields(value))!=sorted(self.fields(self.english[key])):raise ValueError(f'Locale format mismatch: {key}')
        self.strings={**self.english,**translated};self.language=language

    def __call__(self,key,*args,**kwargs):return self.strings[key].format(*args,**kwargs)

    def available(self):
        result=[]
        for path in sorted(self.root.glob('*.json')):
            try:
                translated=self._read(path.stem)
                if any(key in self.english and sorted(self.fields(value))!=sorted(self.fields(self.english[key])) for key,value in translated.items()):continue
                result.append((path.stem,translated.get('meta.language',path.stem)))
            except (OSError,ValueError):continue
        return result
