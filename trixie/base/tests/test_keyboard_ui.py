"""Keyboard menu behavior against representative installed XKB names."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'install'))
from keyboard_ui import choose_layout


class KeyboardMenuTests(unittest.TestCase):
    def setUp(self):
        self.layouts={'fi':'Finnish','se':'Swedish','de':'German','us':'English (US)',
                      'gb':'English (UK)','jp':'Japanese','br':'Portuguese (Brazil)'}
        self.layouts.update({f'zz{i:02}':f'Zone {i:02}' for i in range(21)})

    def choose(self,*answers):
        screen=io.StringIO()
        with redirect_stdout(screen):
            choice=choose_layout(self.layouts,Mock(side_effect=answers))
        return choice,screen.getvalue()

    def test_common_numbers_and_default(self):
        for answer,code in (('','fi'),('1','fi'),('2','se'),('3','de'),('4','us'),('5','gb'),('de','de')):
            with self.subTest(answer=answer):
                chosen,screen=self.choose(answer)
                self.assertEqual(chosen,code)
                self.assertIn('1. Finnish (fi) – default',screen)
                self.assertIn('6. Show all available keyboard layouts',screen)

    def test_browser_uses_dynamic_names_codes_and_numbered_selection(self):
        choice,screen=self.choose('6','5')
        self.assertEqual(choice,'jp')
        self.assertIn('Japanese (jp)',screen)

    def test_search_by_description_and_code(self):
        chosen,screen=self.choose('6','s','BRAZIL','1')
        self.assertEqual(chosen,'br')
        self.assertIn('filter: brazil',screen)
        self.assertEqual(self.choose('6','/zz18','1')[0],'zz18')

    def test_browser_navigation_invalid_input_and_back(self):
        choice,screen=self.choose('blah','6','40','n','n','p','b','4')
        self.assertEqual(choice,'us')
        for label in ('Invalid selection','Enter a number shown','page 2/3','page 3/3'):
            self.assertIn(label,screen)

    def test_no_matches_can_clear_filter(self):
        choice,screen=self.choose('6','s','does not exist','c','5')
        self.assertEqual(choice,'jp')
        self.assertIn('No matching layouts',screen)
