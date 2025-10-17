import unittest


class TestDesignerRoute(unittest.TestCase):
    def test_designer_page_loads(self):
        from reflection_ui.app import app
        with app.test_client() as c:
            r = c.get('/designer')
            assert r.status_code == 200
            html = r.get_data(as_text=True)
            assert 'Reflection Designer' in html

