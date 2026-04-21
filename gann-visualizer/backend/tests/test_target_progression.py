"""
Tests for TargetProgression module
"""
import pytest
from study_tool.target_progression import TargetProgression, FanTargetState, TargetHit


class TestTargetProgression:

    def test_initial_target_is_7_8(self):
        """First target after registration should be 7/8."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)

        assert tp.get_current_target('fan1') == '0.875'

    def test_target_sequence_basic(self):
        """Standard progression: 7/8 → 3/4 → 1/2 → [horizontal, 0.25]."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
        tp.activate_fan('fan1')

        # Hit 0.875
        hit = tp.on_angle_contact('fan1', '0.875', bar_index=10, price=100.0)
        assert hit is not None
        assert hit.target_name == '0.875'
        assert tp.get_current_target('fan1') == '0.75'

        # Hit 0.75
        hit = tp.on_angle_contact('fan1', '0.75', bar_index=20, price=102.0)
        assert hit is not None
        assert tp.get_current_target('fan1') == '0.5'

        # Hit 0.5
        hit = tp.on_angle_contact('fan1', '0.5', bar_index=30, price=105.0)
        assert hit is not None
        # After 0.5, current_target is None (concurrent state)
        assert tp.get_current_target('fan1') is None
        state = tp.get_fan_state('fan1')
        assert 'horizontal' in state.targets_remaining
        assert '0.25' in state.targets_remaining

    def test_horizontal_then_full_coverage(self):
        """After horizontal breach (with 0.25 already hit), go to full_coverage."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
        tp.activate_fan('fan1')

        tp.on_angle_contact('fan1', '0.875', 10, 100.0)
        tp.on_angle_contact('fan1', '0.75', 20, 102.0)
        tp.on_angle_contact('fan1', '0.5', 30, 105.0)

        # Both targets now pending — hit 0.25 first
        hit = tp.on_angle_contact('fan1', '0.25', bar_index=35, price=103.0)
        assert hit is not None
        assert hit.target_name == '0.25'
        assert tp.get_current_target('fan1') == 'horizontal'

        # Now hit horizontal
        hit = tp.on_angle_contact('fan1', 'horizontal', bar_index=40, price=106.0)
        assert hit is not None
        assert tp.get_current_target('fan1') == 'full_coverage'

        # Hit full coverage
        tp.on_angle_contact('fan1', 'full_coverage', bar_index=50, price=110.0)
        assert tp.is_fan_completed('fan1')

    def test_quarter_before_horizontal_keeps_fan_open(self):
        """If 1/4 is reached before horizontal, fan stays open — horizontal remains pending."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
        tp.activate_fan('fan1')

        tp.on_angle_contact('fan1', '0.875', 10, 100.0)
        tp.on_angle_contact('fan1', '0.75', 20, 102.0)
        tp.on_angle_contact('fan1', '0.5', 30, 105.0)

        # 0.25 arrives first — fan stays open
        hit = tp.on_angle_contact('fan1', '0.25', bar_index=35, price=98.0)
        assert hit is not None
        assert hit.target_name == '0.25'
        assert tp.is_fan_completed('fan1') is False
        assert tp.get_current_target('fan1') == 'horizontal'

        # Verify ordering metadata
        state = tp.get_fan_state('fan1')
        assert state.quarter_before_horizontal is True
        assert state.horizontal_target_active is True  # NOT cancelled

        # Now hit horizontal — should proceed to full_coverage
        tp.on_angle_contact('fan1', 'horizontal', bar_index=40, price=106.0)
        assert tp.get_current_target('fan1') == 'full_coverage'

    def test_wrong_target_ignored(self):
        """Breaching an angle that's not the current target should be ignored."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
        tp.activate_fan('fan1')

        # Current target is 0.875, but we report a 0.75 breach — should be ignored
        hit = tp.on_angle_contact('fan1', '0.75', bar_index=10, price=100.0)
        assert hit is None
        assert tp.get_current_target('fan1') == '0.875'

    def test_no_horizontal_target(self):
        """If no horizontal target price is provided, 0.25 is still a concurrent target after 1/2."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=None, full_coverage_target_price=110.0)
        tp.activate_fan('fan1')

        tp.on_angle_contact('fan1', '0.875', 10, 100.0)
        tp.on_angle_contact('fan1', '0.75', 20, 102.0)
        tp.on_angle_contact('fan1', '0.5', 30, 105.0)

        # No horizontal → current_target is None, 0.25 is the only pending target
        state = tp.get_fan_state('fan1')
        assert state.targets_remaining == ['0.25']
        assert tp.get_current_target('fan1') is None

    def test_target_hits_history(self):
        """All target hits should be collected in history."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
        tp.activate_fan('fan1')

        tp.on_angle_contact('fan1', '0.875', 10, 100.0)
        tp.on_angle_contact('fan1', '0.75', 20, 102.0)

        hits = tp.get_all_target_hits()
        assert len(hits) == 2
        assert hits[0].target_name == '0.875'
        assert hits[1].target_name == '0.75'

    def test_remove_fan(self):
        """Removing a fan should clean up its state."""
        tp = TargetProgression()
        tp.register_fan('fan1')

        tp.remove_fan('fan1')
        assert tp.get_fan_state('fan1') is None

    def test_serialization_roundtrip(self):
        """State should survive serialization and deserialization."""
        tp = TargetProgression()
        tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
        tp.activate_fan('fan1')
        tp.on_angle_contact('fan1', '0.875', 10, 100.0)

        state = tp.get_state()
        tp2 = TargetProgression()
        tp2.restore_state(state)

        assert tp2.get_current_target('fan1') == '0.75'
        assert tp2.get_fan_state('fan1').is_validated is True
        assert len(tp2.get_all_target_hits()) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])