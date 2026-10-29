"""Meaningful plan validation checks; textbook replay is verified separately."""

from copy import deepcopy
import unittest

from pdf_exercises import page_numbers, validate_plan


class PlanValidationTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            'requested_exercises': ['1', '3', '5'],
            'dependencies': {'5': ['3']},
            'groups': [
                {'filename': 'one.png', 'exercises': ['1'], 'parts': [
                    {'exercise': '1', 'page': 1, 'box': [10, 10, 90, 50]},
                ]},
                {'filename': 'three-five.png', 'exercises': ['3', '5'], 'parts': [
                    {'exercise': '3', 'page': 1, 'box': [10, 60, 90, 90]},
                    {'exercise': '3', 'page': 2, 'box': [10, 10, 90, 30]},
                    {'exercise': '5', 'page': 2, 'box': [10, 40, 90, 60]},
                ]},
            ],
        }
        self.dimensions = {1: (100, 100), 2: (100, 100)}

    def test_cross_page_dependency_group(self):
        validate_plan(self.plan, self.dimensions)

    def test_missing_requested_exercise(self):
        self.plan['groups'].pop(0)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            validate_plan(self.plan, self.dimensions)

    def test_duplicate_assigned_exercise(self):
        duplicate = deepcopy(self.plan['groups'][0])
        duplicate['filename'] = 'duplicate.png'
        self.plan['groups'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            validate_plan(self.plan, self.dimensions)

    def test_dependency_must_share_group(self):
        group = self.plan['groups'][1]
        part = group['parts'].pop()
        group['exercises'] = ['3']
        self.plan['groups'].append({'filename': 'five.png', 'exercises': ['5'], 'parts': [part]})
        with self.assertRaisesRegex(ValueError, 'requires 3'):
            validate_plan(self.plan, self.dimensions)

    def test_dependency_must_precede_followup(self):
        self.plan['groups'][1]['parts'].reverse()
        with self.assertRaisesRegex(ValueError, 'must precede'):
            validate_plan(self.plan, self.dimensions)

    def test_unassigned_prerequisite_is_context(self):
        self.plan['requested_exercises'] = ['1', '5']
        group = self.plan['groups'][1]
        group['exercises'] = ['5']
        group['context_exercises'] = ['3']
        for part in group['parts'][:2]:
            part['role'] = 'context'
        validate_plan(self.plan, self.dimensions)

    def test_cycle_is_rejected(self):
        self.plan['dependencies']['3'] = ['5']
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            validate_plan(self.plan, self.dimensions)

    def test_outside_page_is_rejected(self):
        self.plan['groups'][0]['parts'][0]['box'][3] = 101
        with self.assertRaisesRegex(ValueError, 'outside PDF'):
            validate_plan(self.plan, self.dimensions)

    def test_unequal_width_is_rejected(self):
        self.plan['groups'][1]['parts'][1]['box'][2] = 89
        with self.assertRaisesRegex(ValueError, 'same rendered width'):
            validate_plan(self.plan, self.dimensions)

    def test_nan_is_rejected(self):
        self.plan['groups'][0]['parts'][0]['box'][1] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite'):
            validate_plan(self.plan, self.dimensions)

    def test_path_traversal_is_rejected(self):
        self.plan['groups'][0]['filename'] = '../outside.png'
        with self.assertRaisesRegex(ValueError, 'single PNG filename'):
            validate_plan(self.plan, self.dimensions)

    def test_gap_requires_explicit_background(self):
        self.plan['groups'][0]['parts'][0]['gap_after_points'] = 5
        with self.assertRaisesRegex(ValueError, 'background_rgb'):
            validate_plan(self.plan, self.dimensions)

    def test_one_based_page_ranges(self):
        self.assertEqual(page_numbers('2-3,1,3', 5), [1, 2, 3])
        with self.assertRaises(ValueError):
            page_numbers('0-2', 5)

    def qualified_context_plan(self):
        return {
            'requested_exercises': ['4D:15'],
            'source_catalog': {
                '4D:15': {'kind': 'exercise', 'section': '4D', 'number': '15'},
                '4C:15': {'kind': 'exercise', 'section': '4C', 'number': '15'},
            },
            'dependencies': {'4D:15': ['4C:15']},
            'groups': [{
                'filename': 'cross-section.png', 'exercises': ['4D:15'],
                'context_exercises': ['4C:15'],
                'parts': [
                    {'exercise': '4C:15', 'role': 'context', 'supports': ['4D:15'],
                     'reason': 'Only the data table is needed.', 'page': 900, 'box': [10, 10, 90, 30]},
                    {'exercise': '4D:15', 'page': 5, 'box': [10, 10, 90, 30]},
                ],
            }],
        }

    def test_distant_same_number_exercises_have_distinct_identities(self):
        validate_plan(self.qualified_context_plan(), {5: (100, 100), 900: (100, 100)})

    def test_qualified_ids_need_catalog(self):
        plan = self.qualified_context_plan()
        del plan['source_catalog']
        with self.assertRaisesRegex(ValueError, 'source_catalog'):
            validate_plan(plan, {5: (100, 100), 900: (100, 100)})

    def test_wrong_section_cannot_match_same_number(self):
        plan = self.qualified_context_plan()
        plan['source_catalog']['4C:15']['section'] = '4D'
        with self.assertRaisesRegex(ValueError, 'expected 4D:15'):
            validate_plan(plan, {5: (100, 100), 900: (100, 100)})

    def test_context_has_specific_purpose(self):
        plan = self.qualified_context_plan()
        del plan['groups'][0]['parts'][0]['reason']
        with self.assertRaisesRegex(ValueError, 'needs a reason'):
            validate_plan(plan, {5: (100, 100), 900: (100, 100)})

    def test_context_cannot_claim_to_support_only_itself(self):
        plan = self.qualified_context_plan()
        plan['groups'][0]['parts'][0]['supports'] = ['4C:15']
        with self.assertRaisesRegex(ValueError, 'must match'):
            validate_plan(plan, {5: (100, 100), 900: (100, 100)})

    def test_unrelated_unselected_source_is_rejected(self):
        plan = self.qualified_context_plan()
        plan['source_catalog']['figure:4.2'] = {'kind': 'figure', 'number': '4.2'}
        plan['groups'][0]['context_exercises'].append('figure:4.2')
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            validate_plan(plan, {5: (100, 100), 900: (100, 100)})

    def test_shared_unselected_context_can_appear_in_two_outputs(self):
        plan = self.qualified_context_plan()
        plan['requested_exercises'].append('4D:17')
        plan['source_catalog']['4D:17'] = {'kind': 'exercise', 'section': '4D', 'number': '17'}
        plan['dependencies']['4D:17'] = ['4C:15']
        other = deepcopy(plan['groups'][0])
        other['filename'] = 'another.png'
        other['exercises'] = ['4D:17']
        other['parts'][0]['supports'] = ['4D:17']
        other['parts'][1]['exercise'] = '4D:17'
        plan['groups'].append(other)
        validate_plan(plan, {5: (100, 100), 900: (100, 100)})

    def test_chained_remote_context(self):
        plan = self.qualified_context_plan()
        plan['source_catalog']['figure:4.2'] = {'kind': 'figure', 'number': '4.2'}
        plan['dependencies']['4C:15'] = ['figure:4.2']
        group = plan['groups'][0]
        group['context_exercises'].append('figure:4.2')
        group['parts'].insert(0, {
            'exercise': 'figure:4.2', 'role': 'context', 'supports': ['4C:15'],
            'reason': 'Legend required to read the retained data.', 'page': 400,
            'box': [10, 10, 90, 30],
        })
        validate_plan(plan, {5: (100, 100), 400: (100, 100), 900: (100, 100)})

    def test_selected_prerequisite_needs_an_assigned_exercise_part(self):
        plan = self.qualified_context_plan()
        plan['requested_exercises'].append('4C:15')
        group = plan['groups'][0]
        group['context_exercises'] = []
        group['exercises'].append('4C:15')
        with self.assertRaisesRegex(ValueError, 'no exercise part'):
            validate_plan(plan, {5: (100, 100), 900: (100, 100)})

    def test_reference_mention_does_not_force_extra_context(self):
        plan = self.qualified_context_plan()
        plan['dependencies'] = {}
        plan['groups'][0]['context_exercises'] = []
        plan['groups'][0]['parts'].pop(0)
        validate_plan(plan, {5: (100, 100)})


if __name__ == '__main__':
    unittest.main()
