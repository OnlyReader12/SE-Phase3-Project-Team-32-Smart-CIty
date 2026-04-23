import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';
import '../providers/dashboard_provider.dart';
import '../providers/auth_provider.dart';
import '../core/api_client.dart';
import '../widgets/actuator_toggle.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Strategy Pattern — MetricPlotStrategy
// Each concrete strategy knows which keys to extract and how to label/color them.
// ─────────────────────────────────────────────────────────────────────────────

abstract class MetricPlotStrategy {
  /// Ordered list of payload keys this strategy can plot.
  List<String> get availableKeys;

  /// Human-readable label for a key.
  String label(String key) => key.replaceAll('_', ' ').toUpperCase();

  /// Color for a key's line.
  Color color(String key);

  /// Unit suffix for tooltip display.
  String unit(String key) => '';
}

class EnergyMetricStrategy extends MetricPlotStrategy {
  @override
  List<String> get availableKeys =>
      ['power_w', 'power', 'voltage', 'current', 'soc', 'load_percent'];

  @override
  Color color(String key) {
    const m = {
      'power_w': Color(0xFFFBBF24),
      'power': Color(0xFFFBBF24),
      'voltage': Color(0xFFFC6D26),
      'current': Color(0xFFFF9933),
      'soc': Color(0xFF4ADE80),
      'load_percent': Color(0xFFEF4444),
    };
    return m[key] ?? const Color(0xFF94A3B8);
  }

  @override
  String unit(String key) {
    const u = {
      'power_w': 'W',
      'power': 'W',
      'voltage': 'V',
      'current': 'A',
      'soc': '%',
      'load_percent': '%',
    };
    return u[key] ?? '';
  }
}

class WaterMetricStrategy extends MetricPlotStrategy {
  @override
  List<String> get availableKeys =>
      ['ph', 'turbidity', 'chlorine', 'flow_rate', 'pressure', 'temperature'];

  @override
  Color color(String key) {
    const m = {
      'ph': Color(0xFF38BDF8),
      'turbidity': Color(0xFF818CF8),
      'chlorine': Color(0xFF4ADE80),
      'flow_rate': Color(0xFF22D3EE),
      'pressure': Color(0xFFF472B6),
      'temperature': Color(0xFFFBBF24),
    };
    return m[key] ?? const Color(0xFF94A3B8);
  }

  @override
  String unit(String key) {
    const u = {
      'ph': 'pH',
      'turbidity': 'NTU',
      'chlorine': 'mg/L',
      'flow_rate': 'L/s',
      'pressure': 'bar',
      'temperature': '°C',
    };
    return u[key] ?? '';
  }
}

class AirMetricStrategy extends MetricPlotStrategy {
  @override
  List<String> get availableKeys =>
      ['pm2_5', 'co2', 'no2', 'o3', 'temperature', 'humidity'];

  @override
  Color color(String key) {
    const m = {
      'pm2_5': Color(0xFFEF4444),
      'co2': Color(0xFFF97316),
      'no2': Color(0xFFFACC15),
      'o3': Color(0xFF4ADE80),
      'temperature': Color(0xFFFBBF24),
      'humidity': Color(0xFF38BDF8),
    };
    return m[key] ?? const Color(0xFF94A3B8);
  }

  @override
  String unit(String key) {
    const u = {
      'pm2_5': 'μg/m³',
      'co2': 'ppm',
      'no2': 'ppb',
      'o3': 'ppb',
      'temperature': '°C',
      'humidity': '%',
    };
    return u[key] ?? '';
  }
}

class GenericMetricStrategy extends MetricPlotStrategy {
  final List<String> _keys;
  GenericMetricStrategy(this._keys);

  @override
  List<String> get availableKeys => _keys;

  @override
  Color color(String key) {
    const palette = [
      Color(0xFF38BDF8), Color(0xFF4ADE80), Color(0xFFFBBF24),
      Color(0xFFEF4444), Color(0xFFA78BFA), Color(0xFFF472B6),
    ];
    final idx = _keys.indexOf(key) % palette.length;
    return palette[idx < 0 ? 0 : idx];
  }
}

/// Factory — picks the right strategy for a domain.
MetricPlotStrategy strategyForDomain(String domain, List<String> discoveredKeys) {
  switch (domain) {
    case 'energy': return EnergyMetricStrategy();
    case 'water':  return WaterMetricStrategy();
    case 'air':    return AirMetricStrategy();
    default:       return GenericMetricStrategy(discoveredKeys);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// NodeDetailScreen
// ─────────────────────────────────────────────────────────────────────────────

class NodeDetailScreen extends ConsumerStatefulWidget {
  final String nodeId;
  final String nodeType;
  final String zone;
  final String domain;
  final String? health;

  const NodeDetailScreen({
    required this.nodeId,
    required this.nodeType,
    required this.zone,
    required this.domain,
    this.health,
    super.key,
  });

  @override
  ConsumerState<NodeDetailScreen> createState() => _NodeDetailScreenState();
}

class _NodeDetailScreenState extends ConsumerState<NodeDetailScreen> {
  Map<String, dynamic>? _latestState;
  bool _loadingState = false;

  // Strategy Pattern state
  late MetricPlotStrategy _strategy;
  Set<String> _selectedMetrics = {};

  // Hover state — stores the index being touched
  int? _touchedIndex;

  @override
  void initState() {
    super.initState();
    _loadState();
  }

  Future<void> _loadState() async {
    setState(() => _loadingState = true);
    try {
      final resp = await ApiClient.instance.get('/actuators/${widget.nodeId}/state');
      setState(() => _latestState = resp.data as Map<String, dynamic>);
    } catch (_) {}
    setState(() => _loadingState = false);
  }

  void _initStrategy(List<Map<String, dynamic>> history) {
    if (history.isEmpty) return;
    final payload = history.first['payload'] as Map<String, dynamic>? ?? {};
    final numericKeys = payload.entries
        .where((e) => e.value is num)
        .map((e) => e.key)
        .toList();

    _strategy = strategyForDomain(widget.domain, numericKeys);

    // Auto-select first 2 available keys that exist in the data
    final initial = _strategy.availableKeys
        .where((k) => numericKeys.contains(k))
        .take(2)
        .toSet();

    // Fallback: if domain strategy has no overlap, use discovered numeric keys
    if (initial.isEmpty) {
      _selectedMetrics = numericKeys.take(2).toSet();
      _strategy = GenericMetricStrategy(numericKeys);
    } else {
      _selectedMetrics = initial;
    }
  }

  Color get _healthColor {
    switch (widget.health) {
      case 'OK':       return const Color(0xFF4ADE80);
      case 'DEGRADED': return const Color(0xFFF59E0B);
      default:         return const Color(0xFFEF4444);
    }
  }

  Color get _domainColor {
    switch (widget.domain) {
      case 'energy': return const Color(0xFFFBBF24);
      case 'water':  return const Color(0xFF38BDF8);
      case 'air':    return const Color(0xFF4ADE80);
      default:       return const Color(0xFF818CF8);
    }
  }

  IconData get _domainIcon {
    switch (widget.domain) {
      case 'energy': return Icons.bolt;
      case 'water':  return Icons.water_drop;
      case 'air':    return Icons.air;
      default:       return Icons.device_hub;
    }
  }

  bool _canToggle(String role) =>
      role != 'ANALYST' && role != 'RESIDENT';

  @override
  Widget build(BuildContext context) {
    final historyAsync = ref.watch(nodeHistoryProvider(widget.nodeId));
    final authState    = ref.watch(authProvider);
    final role = authState.role ?? '';

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.nodeId,
                style: const TextStyle(color: Colors.white, fontSize: 15,
                    fontWeight: FontWeight.bold)),
            Text(widget.nodeType,
                style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Color(0xFF38BDF8)),
            onPressed: () {
              ref.invalidate(nodeHistoryProvider(widget.nodeId));
              _loadState();
            },
          ),
        ],
      ),
      body: historyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Text('Could not load telemetry: $e',
              style: const TextStyle(color: Color(0xFF64748B)))),
        data: (data) {
          final history = (data['history'] as List? ?? [])
              .cast<Map<String, dynamic>>();

          // Initialise strategy once on first data load
          if (_selectedMetrics.isEmpty && history.isNotEmpty) {
            _initStrategy(history);
          }

          final reversed = history.reversed.toList();

          // Discover all numeric payload keys for filter chips
          final allNumericKeys = history.isEmpty ? <String>[] :
              (history.first['payload'] as Map<String, dynamic>? ?? {})
              .entries.where((e) => e.value is num).map((e) => e.key).toList();

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // ── Header badges ────────────────────────────────────────
              Row(children: [
                _badge(widget.zone, Icons.location_on, const Color(0xFF475569)),
                const SizedBox(width: 8),
                _badge(widget.domain, _domainIcon, _domainColor),
                const SizedBox(width: 8),
                _badge(widget.health ?? 'UNKNOWN', Icons.health_and_safety, _healthColor),
              ]),
              const SizedBox(height: 20),

              // ── Current State ────────────────────────────────────────
              Card(
                color: const Color(0xFF1E293B),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Current State',
                        style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                    const SizedBox(height: 8),
                    if (_loadingState)
                      const Center(child: CircularProgressIndicator(strokeWidth: 2))
                    else if (_latestState != null) ...[
                      _stateRow('State', _latestState?['state']?.toString() ?? '—'),
                      _stateRow('Health', _latestState?['health']?.toString() ?? '—'),
                      ...(_latestState?['payload'] as Map<String, dynamic>? ?? {})
                          .entries
                          .map((e) => _stateRow(e.key, e.value?.toString() ?? '—')),
                    ] else
                      const Text('State unavailable',
                          style: TextStyle(color: Color(0xFF64748B))),
                  ]),
                ),
              ),
              const SizedBox(height: 16),

              // ── Actuator toggle ──────────────────────────────────────
              if (_canToggle(role)) ...[
                ActuatorToggle(nodeId: widget.nodeId, label: '${widget.nodeType} Control'),
                const SizedBox(height: 16),
              ],

              // ── Telemetry Chart Card ─────────────────────────────────
              Card(
                color: const Color(0xFF1E293B),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        const Text('Telemetry History',
                            style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                        const Spacer(),
                        Text('${reversed.length} readings',
                            style: const TextStyle(color: Color(0xFF475569), fontSize: 10)),
                      ]),
                      const SizedBox(height: 12),

                      // ── FilterChips — Strategy Pattern Selector ──────
                      if (allNumericKeys.isNotEmpty) ...[
                        const Text('METRICS',
                            style: TextStyle(color: Color(0xFF475569), fontSize: 9,
                                letterSpacing: 1.2)),
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          children: allNumericKeys.map((key) {
                            final selected = _selectedMetrics.contains(key);
                            final color = _strategy.color(key);
                            return FilterChip(
                              label: Text(
                                _strategy.label(key),
                                style: TextStyle(
                                  fontSize: 10,
                                  color: selected ? Colors.white : const Color(0xFF94A3B8),
                                ),
                              ),
                              selected: selected,
                              selectedColor: color.withOpacity(0.25),
                              backgroundColor: const Color(0xFF0F172A),
                              checkmarkColor: color,
                              side: BorderSide(
                                color: selected ? color : const Color(0xFF334155),
                                width: selected ? 1.5 : 1,
                              ),
                              onSelected: (v) => setState(() {
                                if (v) {
                                  _selectedMetrics.add(key);
                                } else if (_selectedMetrics.length > 1) {
                                  _selectedMetrics.remove(key);
                                }
                              }),
                            );
                          }).toList(),
                        ),
                        const SizedBox(height: 16),
                      ],

                      // ── Legend ───────────────────────────────────────
                      if (_selectedMetrics.isNotEmpty) ...[
                        Wrap(
                          spacing: 12,
                          children: _selectedMetrics.map((key) {
                            final unit = _strategy.unit(key);
                            return Row(mainAxisSize: MainAxisSize.min, children: [
                              Container(width: 12, height: 3,
                                  decoration: BoxDecoration(
                                    color: _strategy.color(key),
                                    borderRadius: BorderRadius.circular(2),
                                  )),
                              const SizedBox(width: 4),
                              Text('${_strategy.label(key)}${unit.isNotEmpty ? " ($unit)" : ""}',
                                  style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10)),
                            ]);
                          }).toList(),
                        ),
                        const SizedBox(height: 12),
                      ],

                      // ── Multi-line Chart ─────────────────────────────
                      SizedBox(
                        height: 220,
                        child: reversed.isEmpty || _selectedMetrics.isEmpty
                            ? const Center(child: Text('No data to plot',
                                style: TextStyle(color: Color(0xFF64748B))))
                            : _buildMultiLineChart(reversed),
                      ),

                      // ── Hover Tooltip Panel ──────────────────────────
                      if (_touchedIndex != null && _touchedIndex! < reversed.length)
                        _buildHoverPanel(reversed[_touchedIndex!]),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // ── Full Payload at Latest Point ─────────────────────────
              if (reversed.isNotEmpty)
                _buildPayloadCard(reversed.last),
            ],
          );
        },
      ),
    );
  }

  Widget _buildMultiLineChart(List<Map<String, dynamic>> reversed) {
    final selectedList = _selectedMetrics.toList();

    // Build one line per selected metric
    final lines = selectedList.map((key) {
      final spots = reversed.asMap().entries.map((e) {
        final v = (e.value['payload'] as Map? ?? {})[key];
        return FlSpot(e.key.toDouble(), v is num ? v.toDouble() : 0.0);
      }).toList();

      return LineChartBarData(
        spots: spots,
        isCurved: true,
        color: _strategy.color(key),
        barWidth: 2,
        dotData: const FlDotData(show: false),
        belowBarData: BarAreaData(
          show: selectedList.length == 1,
          color: _strategy.color(key).withOpacity(0.08),
        ),
      );
    }).toList();

    return LineChart(
      LineChartData(
        gridData: FlGridData(
          show: true,
          getDrawingHorizontalLine: (_) =>
              const FlLine(color: Color(0xFF1E3A5F), strokeWidth: 0.8),
          getDrawingVerticalLine: (_) =>
              const FlLine(color: Color(0xFF1E3A5F), strokeWidth: 0.5),
        ),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 44,
              getTitlesWidget: (v, _) => Text(
                v.toStringAsFixed(1),
                style: const TextStyle(color: Color(0xFF475569), fontSize: 8),
              ),
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 22,
              getTitlesWidget: (v, _) {
                final idx = v.toInt();
                if (idx < 0 || idx >= reversed.length) return const SizedBox.shrink();
                if (idx % (reversed.length ~/ 4).clamp(1, 999) != 0) return const SizedBox.shrink();
                final ts = reversed[idx]['timestamp'] as String?;
                if (ts == null) return const SizedBox.shrink();
                try {
                  final dt = DateTime.parse(ts).toLocal();
                  return Text(DateFormat('HH:mm').format(dt),
                      style: const TextStyle(color: Color(0xFF475569), fontSize: 8));
                } catch (_) {
                  return const SizedBox.shrink();
                }
              },
            ),
          ),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        lineTouchData: LineTouchData(
          enabled: true,
          touchCallback: (evt, resp) {
            setState(() {
              if (resp?.lineBarSpots != null && resp!.lineBarSpots!.isNotEmpty) {
                _touchedIndex = resp.lineBarSpots!.first.spotIndex;
              } else if (evt is FlTapUpEvent || evt is FlPanEndEvent) {
                _touchedIndex = null;
              }
            });
          },
          getTouchedSpotIndicator: (barData, spotIndexes) {
            return spotIndexes.map((_) => TouchedSpotIndicatorData(
              FlLine(color: Colors.white.withOpacity(0.4), strokeWidth: 1,
                  dashArray: [4, 4]),
              FlDotData(
                show: true,
                getDotPainter: (spot, _, bar, __) => FlDotCirclePainter(
                  radius: 4,
                  color: bar.color ?? Colors.white,
                  strokeWidth: 1.5,
                  strokeColor: Colors.white,
                ),
              ),
            )).toList();
          },
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => const Color(0xFF0F172A),
            tooltipRoundedRadius: 8,
            getTooltipItems: (spots) {
              return spots.asMap().entries.map((entry) {
                final key = selectedList[entry.key % selectedList.length];
                final unit = _strategy.unit(key);
                return LineTooltipItem(
                  '${_strategy.label(key)}: ${entry.value.y.toStringAsFixed(2)} $unit',
                  TextStyle(
                    color: _strategy.color(key),
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                  ),
                );
              }).toList();
            },
          ),
        ),
        lineBarsData: lines,
      ),
    );
  }

  Widget _buildHoverPanel(Map<String, dynamic> reading) {
    final payload = reading['payload'] as Map<String, dynamic>? ?? {};
    final ts = reading['timestamp'] as String?;
    String timeStr = '—';
    if (ts != null) {
      try {
        timeStr = DateFormat('MMM d, HH:mm:ss').format(DateTime.parse(ts).toLocal());
      } catch (_) {}
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFF334155)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.access_time, size: 11, color: Color(0xFF475569)),
            const SizedBox(width: 4),
            Text(timeStr,
                style: const TextStyle(color: Color(0xFF64748B), fontSize: 10)),
            const Spacer(),
            const Text('ALL PARAMS AT THIS POINT',
                style: TextStyle(color: Color(0xFF334155), fontSize: 9,
                    letterSpacing: 1)),
          ]),
          const SizedBox(height: 8),
          Wrap(
            spacing: 16,
            runSpacing: 4,
            children: payload.entries.map((e) {
              final isSelected = _selectedMetrics.contains(e.key);
              final col = isSelected
                  ? _strategy.color(e.key)
                  : const Color(0xFF64748B);
              final unit = isSelected ? _strategy.unit(e.key) : '';
              return Row(mainAxisSize: MainAxisSize.min, children: [
                if (isSelected)
                  Container(width: 6, height: 6,
                      decoration: BoxDecoration(color: col, shape: BoxShape.circle)),
                if (isSelected) const SizedBox(width: 4),
                Text('${e.key}: ',
                    style: TextStyle(color: col, fontSize: 10,
                        fontWeight: isSelected ? FontWeight.bold : FontWeight.normal)),
                Text('${e.value}${unit.isNotEmpty ? " $unit" : ""}',
                    style: TextStyle(color: isSelected ? Colors.white : const Color(0xFF94A3B8),
                        fontSize: 10)),
              ]);
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildPayloadCard(Map<String, dynamic> reading) {
    final payload = reading['payload'] as Map<String, dynamic>? ?? {};
    final ts = reading['timestamp'] as String?;
    return Card(
      color: const Color(0xFF1E293B),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Text('Latest Telemetry Snapshot',
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
              const Spacer(),
              if (ts != null)
                Text(
                  (){
                    try { return DateFormat('HH:mm:ss').format(DateTime.parse(ts).toLocal()); }
                    catch (_) { return ts; }
                  }(),
                  style: const TextStyle(color: Color(0xFF475569), fontSize: 10),
                ),
            ]),
            const SizedBox(height: 8),
            ...payload.entries.map((e) {
              final isMetric = e.value is num;
              final col = isMetric ? _strategy.color(e.key) : const Color(0xFF64748B);
              return Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(children: [
                  if (isMetric)
                    Container(width: 8, height: 8, margin: const EdgeInsets.only(right: 8),
                        decoration: BoxDecoration(
                          color: _selectedMetrics.contains(e.key) ? col : col.withOpacity(0.3),
                          shape: BoxShape.circle,
                        )),
                  if (!isMetric) const SizedBox(width: 16),
                  Expanded(child: Text(e.key,
                      style: TextStyle(color: col, fontSize: 12))),
                  Text(e.value?.toString() ?? '—',
                      style: TextStyle(
                        color: _selectedMetrics.contains(e.key) ? Colors.white : const Color(0xFF94A3B8),
                        fontSize: 12,
                        fontWeight: _selectedMetrics.contains(e.key)
                            ? FontWeight.bold : FontWeight.normal,
                      )),
                ]),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _badge(String label, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, color: color, size: 12),
        const SizedBox(width: 4),
        Text(label, style: TextStyle(color: color, fontSize: 11,
            fontWeight: FontWeight.w600)),
      ]),
    );
  }

  Widget _stateRow(String key, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(children: [
        Expanded(child: Text(key,
            style: const TextStyle(color: Color(0xFF64748B), fontSize: 12))),
        Text(value,
            style: const TextStyle(color: Colors.white, fontSize: 12,
                fontWeight: FontWeight.w500)),
      ]),
    );
  }
}
