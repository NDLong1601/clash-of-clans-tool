"""Configuration values that the desktop panel sends to the bot."""

import threading
import unittest
from unittest.mock import Mock

from cocmagic.bot_engine import BotEngine
from cocmagic.gui import build_settings, parse_amount


class PanelSettingsTests(unittest.TestCase):
    def test_money_input_accepts_vietnamese_shorthand(self):
        self.assertEqual(9_000_000, parse_amount("9tr"))
        self.assertEqual(9_000_000, parse_amount("9.000.000"))
        self.assertEqual(1_500_000, parse_amount("1,5tr"))
        self.assertEqual(500_000, parse_amount("500k"))

    def test_mode_and_values_are_applied_without_losing_other_options(self):
        original = {"use_king": False, "upgrade_walls": True}
        fields = {"min_gold": "500k", "min_elixir": "500k",
                  "min_farm": "45", "star_target": "2",
                  "farm_battle_timeout": "85", "wall_resource": "9tr",
                  "wall_type": "both"}
        updated = build_settings(original, fields, False)
        self.assertEqual(9_000_000, updated["wall_resource"])
        self.assertEqual(2, updated["star_target"])
        self.assertFalse(updated["upgrade_walls"])
        self.assertTrue(updated["event_mode"])
        self.assertEqual("dark", updated["event_resource_priority"])
        self.assertFalse(updated["use_king"])

    def test_bonus_priority_is_saved_and_normal_mode_turns_reward_handling_off(self):
        fields = {"min_gold": "0", "min_elixir": "0", "min_farm": "45",
                  "star_target": "1", "farm_battle_timeout": "85",
                  "wall_resource": "0", "wall_type": "gold",
                  "event_resource_priority": "elixir"}
        event = build_settings({}, fields, False)
        self.assertTrue(event["event_mode"])
        self.assertEqual("elixir", event["event_resource_priority"])
        normal = build_settings(event, fields, True)
        self.assertFalse(normal["event_mode"])
        self.assertTrue(normal["upgrade_walls"])
        fields["event_resource_priority"] = "troop"
        with self.assertRaises(ValueError):
            build_settings(event, fields, False)

    def test_attack_tuning_is_validated(self):
        fields = {"min_gold": "0", "min_elixir": "0", "min_farm": "45",
                  "star_target": "1", "farm_battle_timeout": "85",
                  "wall_resource": "0", "wall_type": "both",
                  "electro_per_direction": "3", "warden_ability_delay": "10"}
        updated = build_settings({}, fields, False)
        self.assertEqual(3, updated["electro_per_direction"])
        self.assertEqual(10, updated["warden_ability_delay"])
        fields["electro_per_direction"] = "0"
        with self.assertRaises(ValueError):
            build_settings({}, fields, False)

    def test_bad_time_and_star_count_are_rejected(self):
        fields = {"min_gold": "0", "min_elixir": "0", "min_farm": "90",
                  "star_target": "4", "farm_battle_timeout": "85",
                  "wall_resource": "9tr", "wall_type": "both"}
        with self.assertRaises(ValueError):
            build_settings({}, fields, True)
        fields["star_target"] = "1"
        with self.assertRaises(ValueError):
            build_settings({}, fields, True)

    def test_engine_can_start_from_gui_worker_thread(self):
        engine = BotEngine({})
        engine._connect_adb = Mock(return_value=False)
        results = []
        worker = threading.Thread(target=lambda: results.append(engine.start()))
        worker.start()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual([False], results)


if __name__ == "__main__":
    unittest.main()
