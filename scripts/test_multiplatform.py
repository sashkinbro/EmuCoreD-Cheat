# SPDX-License-Identifier: MIT
import unittest
import hashlib
import json
import pathlib
import tempfile
from unittest.mock import patch
import validate_multiplatform
from build_multiplatform import parse_cht, parse_dat, parse_dolphin, match_identity, code_format, IdentityMatcher


class CatalogContracts(unittest.TestCase):
    @staticmethod
    def matcher(*names):
        return IdentityMatcher({name: [{'name': name, 'romName': name + '.nds', 'sha1': str(i)}]
                                for i, name in enumerate(names)})

    def test_unique_missing_language_metadata_preserves_the_dat_release(self):
        matcher = self.matcher('Game (Europe) (En,Fr)')
        found = matcher.match('Game (Europe)')
        self.assertEqual('Game (Europe) (En,Fr)', found[0]['name'])
        self.assertEqual('unique-qualified-dat-alias', found[0]['mappingEvidence']['rule'])
        self.assertEqual([], matcher.match('Game (Europe) (En,De)'))

    def test_missing_language_metadata_is_rejected_for_multiple_editions(self):
        matcher = self.matcher('Game (Europe) (En,Fr)', 'Game (Europe) (En,De)')
        self.assertEqual([], matcher.match('Game (Europe)'))
        self.assertEqual('Game (Europe) (En,Fr)', matcher.match('Game (Europe) (En,Fr)')[0]['name'])

    def test_aliases_keep_region_revision_hacks_and_enhancement_qualifiers(self):
        matcher = self.matcher('Game & Watch (USA, Europe) (En,Fr) (Rev 1) (SGB Enhanced)')
        self.assertTrue(matcher.match('Game _ Watch (Europe, USA) (Rev 1) (SGB Enhanced) (Xploder)'))
        for title in ['Game & Watch (USA) (Rev 1) (SGB Enhanced)',
                      'Game & Watch (USA, Europe) (SGB Enhanced)',
                      'Game & Watch (USA, Europe) (Rev 1)',
                      'Game & Watch (USA, Europe) (Rev 2) (SGB Enhanced)',
                      'Game & Watch (USA, Europe) (Rev 1) (SGB Enhanced) (Hack)',
                      'Game & Watch']:
            self.assertEqual([], matcher.match(title), title)

    def test_typography_article_and_rom_filename_aliases_are_unique(self):
        matcher = self.matcher("Adventure, The (USA)")
        self.assertTrue(matcher.match('The Adventure (USA)'))
        self.assertTrue(matcher.match('adventure, the (USA)'))
        self.assertEqual([], matcher.match('Adventure (USA)'))
        matcher = IdentityMatcher({'Official (USA)': [{'romName': 'Source Alias (USA).gba'}]})
        self.assertTrue(matcher.match('Source Alias (USA)'))

    def test_normalization_collision_is_rejected_and_unknown_suffix_is_retained(self):
        matcher = self.matcher('Game & Watch (USA)', 'Game _ Watch (USA)')
        self.assertEqual([], matcher.match('GAME & WATCH (USA)'))
        self.assertEqual([], matcher.match('Game & Watch (USA) (Game Genie Edition)'))
        self.assertEqual([], matcher.match('Game & Watch (USA) (diff)'))

    def test_ds_pairs_and_categories_are_not_executable_cheats(self):
        blocks = parse_cht('cheats = 2\ncheat0_desc = "Category"\ncheat1_desc = "Lives"\ncheat1_code = "02000000+00000063+D2000000+00000000"', 'nds')
        self.assertEqual(1, len(blocks))
        self.assertEqual(['02000000 00000063', 'D2000000 00000000'], blocks[0]['lines'])
        self.assertEqual('nds-action-replay', blocks[0]['format'])

    def test_retroarch_memory_handlers_are_never_guessed_as_native_codes(self):
        text = 'cheat0_desc = "Memory"\ncheat0_handler = 1\ncheat0_code = "00000001"\ncheat0_address = 42\ncheat0_value = 3'
        self.assertEqual('retroarch-memory', parse_cht(text, 'gb')[0]['format'])

    def test_gba_device_syntax_is_distinct(self):
        self.assertEqual('gba-codebreaker', code_format('gba', '8201227C+FFFF', '', {}))
        self.assertEqual('gba-device-unspecified', code_format('gba', 'DEADBEEF+CAFEBABE', '', {}))

    def test_gba_device_title_does_not_make_malformed_codes_executable(self):
        self.assertEqual('gba-device-unspecified', code_format('gba', 'DEADBEEF+ZAFEBABE', 'Game (Action Replay)', {}))
        self.assertEqual('gba-device-unspecified', code_format('gba', 'DEADBEEF', 'Game (GameShark)', {}))
        self.assertEqual('gba-action-replay', code_format('gba', 'DEADBEEF+CAFEBABE', 'Game (Action Replay)', {}))
        self.assertEqual('gba-gameshark', code_format('gba', 'DEADBEEF CAFEBABE', 'Game (GameShark)', {}))

    def test_identity_requires_exact_region_and_revision(self):
        records = parse_dat('game (\n name "Shared (USA) (Rev 1)"\n region "USA"\n rom ( name "game.gba" size 32 crc 12345678 md5 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA sha1 BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB serial "ABCE" )\n)')
        self.assertEqual('12345678', match_identity('Shared (USA) (Rev 1)', records)[0]['crc32'])
        self.assertEqual([], match_identity('Shared (USA)', records))
        self.assertEqual([], match_identity('Shared (Europe) (Rev 1)', records))
        self.assertEqual(['12345678'], [item['crc32'] for item in match_identity('Shared (USA) (Rev 1) (CodeBreaker)', records)])
        self.assertEqual([], match_identity('Shared (USA) (Rev 1) (Code Breaker Edition)', records))

    def test_dolphin_types_and_disabled_state_are_preserved(self):
        text = '[ActionReplay]\n$Lives\n00000000 00000063\n[Gecko]\n$Jump [Author]\n04000000 60000000\n[Gecko_Enabled]\n$Jump\n[Video_Hacks]\nFake = True'
        blocks = parse_dolphin(text)
        self.assertEqual(['dolphin-action-replay', 'dolphin-gecko'], [b['format'] for b in blocks])
        self.assertTrue(all(not b['enabled'] for b in blocks))
        self.assertEqual('Author', blocks[1]['author'])

    def test_dolphin_malformed_line_quarantines_entire_block_instead_of_partial_code(self):
        blocks = parse_dolphin('[ActionReplay]\n$Broken\n04000000 60000000\n021D5678 00000BOC')
        self.assertEqual('dolphin-action-replay-unparsed', blocks[0]['format'])
        self.assertEqual(['021D5678 00000BOC'], blocks[0]['unparsedLines'])

    def test_dolphin_whitespace_and_inline_credit_do_not_drop_guest_instructions(self):
        blocks = parse_dolphin('[Gecko]\n$Jump\n04000000  60000000\n04000004 60000000 [Author]')
        self.assertEqual(['04000000 60000000', '04000004 60000000'], blocks[0]['lines'])

    def test_encrypted_action_replay_has_explicit_format_and_mixed_block_is_quarantined(self):
        encrypted = 'ABCD-EFGH-JKLMN'
        blocks = parse_dolphin('[ActionReplay]\n$Encrypted\n' + encrypted)
        self.assertEqual('dolphin-action-replay-encrypted', blocks[0]['format'])
        self.assertEqual([encrypted], blocks[0]['lines'])
        mixed = parse_dolphin('[ActionReplay]\n$Mixed\n04000000 60000000\n' + encrypted)
        self.assertEqual('dolphin-action-replay-mixed-unparsed', mixed[0]['format'])

    def test_encrypted_action_replay_is_never_recognized_as_gecko(self):
        blocks = parse_dolphin('[Gecko]\n$Invalid\nABCD-EFGH-JKLMN')
        self.assertEqual('dolphin-gecko-unparsed', blocks[0]['format'])
        self.assertEqual(['ABCD-EFGH-JKLMN'], blocks[0]['unparsedLines'])

    def test_ds_malformed_pair_is_not_partially_exported_as_action_replay(self):
        blocks = parse_cht('cheat0_desc = "Broken"\ncheat0_code = "02000000+00000063+D2000000"', 'nds')
        self.assertEqual('unclassified', blocks[0]['format'])

    def test_payload_validation_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            payload = b'{"valid":true}'
            (root / 'pack.json').write_bytes(payload)
            entry = {'path': 'pack.json', 'sizeBytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
            with patch.object(validate_multiplatform, 'ROOT', root):
                self.assertEqual({'valid': True}, validate_multiplatform.checked_file(entry))
                (root / 'pack.json').write_bytes(b'{"valid":null}')
                with self.assertRaises(AssertionError):
                    validate_multiplatform.checked_file(entry)

    def test_payload_validation_rejects_paths_outside_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(validate_multiplatform, 'ROOT', pathlib.Path(temporary)):
                with self.assertRaises(AssertionError):
                    validate_multiplatform.checked_file({'path': '../escape.json', 'sizeBytes': 1, 'sha256': ''})


if __name__ == '__main__':
    unittest.main()
