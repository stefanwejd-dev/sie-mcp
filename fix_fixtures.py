import re

with open('tests/test_spiris_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace test_hamta_kontotransaktioner(self, mock_spiris_klient):
# with test_hamta_kontotransaktioner(self):
#     from unittest.mock import MagicMock
#     mock_spiris_klient = MagicMock()
content = re.sub(
    r'def test_hamta_kontotransaktioner\(self, mock_spiris_klient\):',
    'def test_hamta_kontotransaktioner(self):\n        from unittest.mock import MagicMock\n        mock_spiris_klient = MagicMock()',
    content
)

content = re.sub(
    r'def test_hamta_kontosaldon\(self, mock_spiris_klient\):',
    'def test_hamta_kontosaldon(self):\n        from unittest.mock import MagicMock\n        mock_spiris_klient = MagicMock()',
    content
)

content = re.sub(
    r'def test_hamta_momsoversikt\(self, mock_spiris_klient\):',
    'def test_hamta_momsoversikt(self):\n        from unittest.mock import MagicMock\n        mock_spiris_klient = MagicMock()',
    content
)

with open('tests/test_spiris_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
