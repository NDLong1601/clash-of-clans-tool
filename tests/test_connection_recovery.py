"""Connection loss must interrupt battle input until the reload wait ends."""

import os
import threading
import unittest
from unittest.mock import Mock, patch

import cv2

from cocmagic import config
from cocmagic.adb_controller import ADBController
from cocmagic.bot_engine import BotEngine
from cocmagic.modules.farm_module import CardSlot, ComboProfile, FarmModule, FarmState, SpellProgress
from cocmagic.ui_dialogs import find_connection_retry
from cocmagic.run_coordinator import RunCoordinator


class ConnectionRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures = os.path.join(config.BASE_DIR, "tests", "fixtures")
        cls.dialog = cv2.imread(os.path.join(fixtures, "connection_lost.png"))
        cls.battle = cv2.imread(os.path.join(fixtures, "battle_screen.png"))

    def test_user_dialog_locates_try_again(self):
        point = find_connection_retry(ADBController(settings={}), self.dialog)
        self.assertIsNotNone(point)
        self.assertTrue(420 < point[0] < 550 and 510 < point[1] < 550)

    def test_battle_and_end_battle_confirmation_are_not_network_errors(self):
        adb = ADBController(settings={})
        self.assertIsNone(find_connection_retry(adb, self.battle))
        confirmation = cv2.imread(os.path.join(config.BASE_DIR, "tests", "fixtures",
                                                "end_battle_confirm.png"))
        self.assertIsNone(find_connection_retry(adb, confirmation))

    def test_title_without_retry_button_does_not_trigger_a_blind_tap(self):
        image = self.dialog.copy()
        image[505:570, 400:650] = image[350, 800]
        self.assertIsNone(find_connection_retry(ADBController(settings={}), image))

    def make_engine(self):
        engine = BotEngine({"auto_train": False})
        engine.adb = ADBController(settings={})
        engine.adb.tap = Mock(return_value=True)
        engine.adb.tap_many = Mock(return_value=True)
        engine.wall_mod = Mock(walls_upgraded=0)
        engine.farm_mod = FarmModule(engine.adb, None, Mock(), engine.settings,
                                     recovery_handler=engine._handle_connection_lost)
        engine.coordinator = RunCoordinator(engine.adb.device, {"main": engine.farm_mod}, "main")
        return engine

    @patch("cocmagic.bot_engine.BotEngine._wait")
    def test_connection_loss_aborts_attack_and_clears_stale_battle_cache(self, sleep):
        engine = self.make_engine()
        engine.adb.screenshot = Mock(return_value=self.dialog)
        farm = engine.farm_mod
        farm.state = FarmState.ATTACKING
        farm._initial_trained = True
        farm._home_verified = True
        farm._button_cache["home_attack"] = (80, 800)
        farm._combo_profile = ComboProfile([CardSlot(180, 840, "troop")], [], (900, 1600))
        farm._deployed_hero_slots["warden"] = (670, 840)
        farm._pending_spells[CardSlot(811, 840, "spell", "rage")] = SpellProgress(
            cast_index=2, unconfirmed_before=self.battle)
        farm._deploy_all_troops = Mock()
        order = []
        engine.adb.tap.side_effect = lambda *a, **kw: order.append("retry") or True
        sleep.side_effect = lambda seconds: order.append(("wait", seconds))

        self.assertTrue(farm.tick())

        self.assertEqual(["retry", ("wait", 10)], order)
        self.assertEqual(FarmState.RECOVERING, farm.state)
        self.assertIsNone(farm._combo_profile)
        self.assertFalse(farm._home_verified)
        self.assertEqual({}, farm._button_cache)
        self.assertEqual({}, farm._deployed_hero_slots)
        self.assertEqual({}, farm._pending_spells)
        self.assertTrue(farm._initial_trained)
        farm._deploy_all_troops.assert_not_called()
        engine.adb.tap_many.assert_not_called()

    @patch("cocmagic.bot_engine.BotEngine._wait")
    def test_connection_loss_mid_spell_sequence_prevents_next_cast(self, sleep):
        engine = self.make_engine()
        engine.adb.screenshot = Mock(side_effect=[self.battle, self.dialog])
        farm = engine.farm_mod
        farm.state = FarmState.ATTACKING
        farm._combo_profile = ComboProfile([CardSlot(811, 840, "spell", "rage")], [], (900, 1600))
        farm._attack_tactics = Mock()
        farm._attack_tactics.spell_target.return_value = (700, 400)
        farm._card_depleted = Mock(return_value=False)
        farm._handle_state = farm._deploy_spells

        self.assertTrue(farm.tick())

        engine.adb.tap_many.assert_called_once_with([(811, 840), (700, 400)], interval=.03)
        self.assertEqual(FarmState.RECOVERING, farm.state)
        self.assertIn(unittest.mock.call(10), sleep.call_args_list)

    @patch("cocmagic.bot_engine.BotEngine._wait")
    def test_stop_button_interrupts_reload_wait(self, sleep):
        engine = self.make_engine()
        engine.stop_event = threading.Event()
        engine.stop_event.set()
        self.assertTrue(engine._handle_connection_lost(self.dialog))
        sleep.assert_not_called()
        engine.adb.tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
