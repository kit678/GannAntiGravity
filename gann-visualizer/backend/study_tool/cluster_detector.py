import pandas as pd
from typing import Dict, Any, Optional

class ClusterDetector:
    """
    Detects consolidation phases (clusters) using Intersection over Union (IoU) 
    of candle ranges and inside bar patterns.
    Maintains a bounding box that expands dynamically and only resolves on a decisive close outside.
    """
    def __init__(self, iou_threshold: float = 0.70):
        self.iou_threshold = iou_threshold
        self.in_cluster = False
        self.cluster_high: Optional[float] = None
        self.cluster_low: Optional[float] = None
        self.cluster_start_idx: Optional[int] = None
        self.cluster_bars = 0
        self.previous_candle: Optional[pd.Series] = None

    def _calculate_iou(self, candle1: pd.Series, candle2: pd.Series) -> float:
        """Calculate the Range Intersection over Union between two candles."""
        # Intersection
        min_high = min(candle1['High'], candle2['High'])
        max_low = max(candle1['Low'], candle2['Low'])
        overlap = max(0.0, min_high - max_low)

        # Union
        max_high = max(candle1['High'], candle2['High'])
        min_low = min(candle1['Low'], candle2['Low'])
        union = max_high - min_low
        
        if union == 0:
            return 1.0
            
        return overlap / union

    def _is_inside_bar(self, current: pd.Series, previous: pd.Series) -> bool:
        """Check if current candle is completely inside the previous candle's range."""
        return current['High'] <= previous['High'] and current['Low'] >= previous['Low']

    def process_candle(self, current_candle: pd.Series, bar_index: int) -> Dict[str, Any]:
        """
        Process the current candle to detect cluster formation, expansion, or resolution.
        Returns the current cluster state.
        """
        # Ensure we handle both capitalized and lowercase keys
        c_high = current_candle.get('High', current_candle.get('high'))
        c_low = current_candle.get('Low', current_candle.get('low'))
        c_close = current_candle.get('Close', current_candle.get('close'))

        if self.previous_candle is None:
            self.previous_candle = current_candle
            return self.get_state()

        p_high = self.previous_candle.get('High', self.previous_candle.get('high'))
        p_low = self.previous_candle.get('Low', self.previous_candle.get('low'))

        if not self.in_cluster:
            # Check for initiation
            # Manual IoU calculation to avoid key errors
            # Intersection
            min_high = min(c_high, p_high)
            max_low = max(c_low, p_low)
            overlap = max(0.0, min_high - max_low)

            # Union
            max_high = max(c_high, p_high)
            min_low = min(c_low, p_low)
            union = max_high - min_low
            
            iou = overlap / union if union > 0 else 1.0
            is_inside = c_high <= p_high and c_low >= p_low
            
            if iou >= self.iou_threshold or is_inside:
                self.in_cluster = True
                self.cluster_high = max_high
                self.cluster_low = min_low
                self.cluster_start_idx = bar_index - 1
                self.cluster_bars = 2
        else:
            # Check for resolution
            if c_close > self.cluster_high or c_close < self.cluster_low:
                self._reset()
            else:
                # Still in cluster, expand box if wicks push outside the current boundaries
                self.cluster_high = max(self.cluster_high, c_high)
                self.cluster_low = min(self.cluster_low, c_low)
                self.cluster_bars += 1

        self.previous_candle = current_candle
        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state of the cluster detector."""
        return {
            'in_cluster': self.in_cluster,
            'cluster_high': self.cluster_high,
            'cluster_low': self.cluster_low,
            'cluster_bars': self.cluster_bars,
            'previous_candle': self.previous_candle.to_dict() if hasattr(self.previous_candle, 'to_dict') else (dict(self.previous_candle) if self.previous_candle is not None else None)
        }

    def restore_state(self, state: Dict[str, Any]):
        """Restores the state of the cluster detector."""
        self.in_cluster = state.get('in_cluster', False)
        self.cluster_high = state.get('cluster_high')
        self.cluster_low = state.get('cluster_low')
        self.cluster_bars = state.get('cluster_bars', 0)
        import pandas as pd
        prev = state.get('previous_candle')
        if prev is not None:
            self.previous_candle = pd.Series(prev)
        else:
            self.previous_candle = None

    def _reset(self):
        """Reset the cluster state after a decisive breakout."""
        self.in_cluster = False
        self.cluster_high = None
        self.cluster_low = None
        self.cluster_start_idx = None
        self.cluster_bars = 0
