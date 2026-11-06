"""Shared, dependency-free settings for TC catalog reads only."""
import json
import os
from pathlib import Path
import tempfile


DEFAULT_CATALOG_TIMEOUT_SECONDS = 100


def validate_catalog_timeout_seconds(value):
    if type(value) is not int or not 1 <= value <= 600:
        raise ValueError('TC 목록 읽기 제한시간은 1~600초 사이의 정수여야 합니다.')
    return value


class CatalogSettings:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            raw = self.path.read_text(encoding='utf-8-sig')
        except FileNotFoundError:
            return {'catalog_timeout_seconds': DEFAULT_CATALOG_TIMEOUT_SECONDS}
        value = json.loads(raw)
        if not isinstance(value, dict) or 'catalog_timeout_seconds' not in value:
            raise ValueError('TC 목록 읽기 설정 파일 형식이 올바르지 않습니다.')
        return {'catalog_timeout_seconds': validate_catalog_timeout_seconds(value['catalog_timeout_seconds'])}

    def save(self, seconds):
        value = {'catalog_timeout_seconds': validate_catalog_timeout_seconds(seconds)}
        # Validate before creating anything; replace only a completely flushed file.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError('TC 목록 읽기 설정은 링크 파일에 저장할 수 없습니다.')
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + '.', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return value
