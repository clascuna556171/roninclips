import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

import engine
from engine import gemini_extract_text, llm_complete, load_api_keys, pick_gemini_models


class TestLoadApiKeys(unittest.TestCase):
    def test_env_file_wins_for_set_keys_and_blank_keeps_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '.env')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('GROQ_API_KEY="gsk_new_from_file"\nGEMINI_API_KEY=\nDB_CONNECTION=mysql\n')
            environ = {'GROQ_API_KEY': 'gsk_stale', 'GEMINI_API_KEY': 'AIza_kept', 'DB_CONNECTION': 'sqlite'}
            load_api_keys(path, environ)
        self.assertEqual(environ['GROQ_API_KEY'], 'gsk_new_from_file')
        self.assertEqual(environ['GEMINI_API_KEY'], 'AIza_kept')
        self.assertEqual(environ['DB_CONNECTION'], 'sqlite')  # only the API keys are overridden

    def test_missing_file_is_ignored(self):
        environ = {}
        load_api_keys(os.path.join(tempfile.gettempdir(), 'no_such_rc.env'), environ)
        self.assertEqual(environ, {})


class TestGeminiHelpers(unittest.TestCase):
    def test_pick_models_prefers_override_then_curated_then_flash(self):
        live = ['gemini-2.5-pro', 'gemini-2.5-flash', 'text-embedding-004', 'gemini-2.5-flash-preview-tts',
                'gemini-3-flash', 'gemma-3-27b-it']
        models = pick_gemini_models(live, custom_model='gemini-custom')
        self.assertEqual(models[:3], ['gemini-custom', 'gemini-2.5-flash', 'gemini-3-flash'])
        self.assertIn('gemini-2.5-pro', models)
        self.assertFalse(any('tts' in m or 'embedding' in m or 'gemma' in m for m in models))

    def test_pick_models_uses_curated_list_when_listing_failed(self):
        self.assertEqual(pick_gemini_models([])[0], 'gemini-2.5-flash')

    def test_extract_text_skips_thoughts(self):
        payload = {'candidates': [{'content': {'parts': [
            {'text': 'thinking...', 'thought': True},
            {'text': '[{"start": "00:00:01"'},
            {'text': '}]'},
        ]}}]}
        self.assertEqual(gemini_extract_text(payload), '[{"start": "00:00:01"}]')

    def test_extract_text_raises_on_block_or_empty(self):
        with self.assertRaises(RuntimeError):
            gemini_extract_text({'promptFeedback': {'blockReason': 'SAFETY'}})
        with self.assertRaises(RuntimeError):
            gemini_extract_text({'candidates': [{'content': {'parts': []}, 'finishReason': 'MAX_TOKENS'}]})


class TestLlmComplete(unittest.TestCase):
    def run_with(self, env, groq_result=(None, RuntimeError('groq down')), gemini_result=('gemini text', None)):
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(engine, 'groq_complete', return_value=groq_result) as groq, \
                mock.patch.object(engine, 'gemini_complete', return_value=gemini_result) as gemini, \
                mock.patch.object(engine, 'get_gemini_models', return_value=['gemini-2.5-flash']):
            result = llm_complete('prompt', ['llama'])
        return result, groq, gemini

    def test_groq_success_never_calls_gemini(self):
        result, groq, gemini = self.run_with({'GROQ_API_KEY': 'g', 'GEMINI_API_KEY': 'm'}, groq_result=('groq text', None))
        self.assertEqual(result, ('groq text', None))
        gemini.assert_not_called()

    def test_groq_failure_falls_back_to_gemini(self):
        result, groq, gemini = self.run_with({'GROQ_API_KEY': 'g', 'GEMINI_API_KEY': 'm'})
        self.assertEqual(result, ('gemini text', None))
        groq.assert_called_once()
        gemini.assert_called_once_with('prompt', ['gemini-2.5-flash'])

    def test_gemini_only_skips_groq(self):
        result, groq, gemini = self.run_with({'GROQ_API_KEY': '', 'GEMINI_API_KEY': 'm'})
        self.assertEqual(result, ('gemini text', None))
        groq.assert_not_called()

    def test_both_fail_returns_last_error(self):
        result, _, _ = self.run_with({'GROQ_API_KEY': 'g', 'GEMINI_API_KEY': 'm'},
                                     gemini_result=(None, RuntimeError('gemini quota')))
        self.assertIsNone(result[0])
        self.assertIn('gemini quota', str(result[1]))

    def test_no_keys_explains_where_to_add_one(self):
        result, groq, gemini = self.run_with({'GROQ_API_KEY': '', 'GEMINI_API_KEY': ''})
        self.assertIsNone(result[0])
        self.assertIn('API KEYS', str(result[1]))
        groq.assert_not_called()
        gemini.assert_not_called()


if __name__ == '__main__':
    unittest.main()
