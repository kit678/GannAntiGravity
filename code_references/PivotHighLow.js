function PivotHighLow(PineJS) {
  return {
    name: 'Pivot_High_Low',
    
    metainfo: {
      _metainfoVersion: 53,
      id: 'Pivot_High_Low@tv-basicstudies-1',
      description: 'Pivot High/Low',
      shortDescription: 'Pivot',
      
      is_price_study: true,
      isCustomIndicator: true,
      
      plots: [
        { id: 'ph', type: 'shapes' },
        { id: 'pl', type: 'shapes' }
      ],
      
      styles: {
        ph: {
          title: 'Pivot Highs',
          plottype: 'shape_triangle_down',
          location: 'AboveBar',
          size: 'small'
        },
        pl: {
          title: 'Pivot Lows',
          plottype: 'shape_triangle_up',
          location: 'BelowBar',
          size: 'small'
        }
      },
      
      defaults: {
        styles: {
          ph: { color: '#FF4433', plottype: 'shape_triangle_down', location: 'AboveBar', visible: true, size: 'small' },
          pl: { color: '#22CC22', plottype: 'shape_triangle_up', location: 'BelowBar', visible: true, size: 'small' }
        },
        inputs: { len: 5 }
      },
      
      inputs: [
        {
          id: 'len',
          name: 'Length',
          defval: 5,
          type: 'integer',
          min: 1,
          max: 10
        }
      ],
      
      format: { type: 'price', precision: 2 }
    },
    
    constructor: function() {
      this.init = function(context, inputCallback) {
        this._context = context;
        this._input = inputCallback;
        
        const len = this._input(0);
        this._window = 2 * len + 1;
        this._buffer = [];
      };
      
      this.main = function(context, inputCallback) {
        this._context = context;
        this._input = inputCallback;
        const len = this._input(0);
        
        this._buffer.push({
          high: PineJS.Std.high(this._context),
          low: PineJS.Std.low(this._context)
        });
        
        if (this._buffer.length > this._window) {
          this._buffer.shift();
        }
        
        if (this._buffer.length < this._window) {
          return [undefined, undefined];
        }
        
        const midIdx = len;
        const midHigh = this._buffer[midIdx].high;
        const midLow = this._buffer[midIdx].low;
        
        const isHigh = this._buffer.every((bar, i) => 
          i === midIdx || midHigh > bar.high
        );
        
        const isLow = this._buffer.every((bar, i) => 
          i === midIdx || midLow < bar.low
        );
        
        return [
          isHigh ? { value: midHigh, offset: -len } : undefined,
          isLow ? { value: midLow, offset: -len } : undefined
        ];
      };
    }
  };
} 