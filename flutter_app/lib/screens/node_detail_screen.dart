import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fl_chart/fl_chart.dart';
import '../providers/dashboard_provider.dart';
import '../providers/auth_provider.dart';
import '../core/api_client.dart';
import '../widgets/actuator_toggle.dart';

/// NodeDetailScreen — shows full telemetry + history chart + actuator toggle.
/// Navigate to this screen from any dashboard node tile.
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
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Header badges ────────────────────────────────────────────
          Row(children: [
            _badge(widget.zone, Icons.location_on, const Color(0xFF475569)),
            const SizedBox(width: 8),
            _badge(widget.domain, _domainIcon, _domainColor),
            const SizedBox(width: 8),
            _badge(widget.health ?? 'UNKNOWN', Icons.health_and_safety, _healthColor),
          ]),
          const SizedBox(height: 20),

          // ── Current State ────────────────────────────────────────────
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

          // ── Actuator toggle ──────────────────────────────────────────
          if (_canToggle(role)) ...[
            ActuatorToggle(nodeId: widget.nodeId, label: '${widget.nodeType} Control'),
            const SizedBox(height: 16),
          ],

          // ── History chart ────────────────────────────────────────────
          Card(
            color: const Color(0xFF1E293B),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('24h History',
                    style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                const SizedBox(height: 12),
                SizedBox(
                  height: 180,
                  child: historyAsync.when(
                    loading: () => const Center(child: CircularProgressIndicator()),
                    error: (e, _) => Center(
                      child: Text('History unavailable',
                          style: const TextStyle(color: Color(0xFF64748B))),
                    ),
                    data: (data) => _buildHistoryChart(data),
                  ),
                ),
              ]),
            ),
          ),
          const SizedBox(height: 16),

          // ── Raw payload from history ─────────────────────────────────
          historyAsync.maybeWhen(
            data: (data) {
              final history = (data['history'] as List? ?? [])
                  .cast<Map<String, dynamic>>();
              if (history.isEmpty) return const SizedBox.shrink();
              final latest = history.first;
              return Card(
                color: const Color(0xFF1E293B),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Latest Telemetry',
                          style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                      const SizedBox(height: 8),
                      ...(latest['payload'] as Map<String, dynamic>? ?? {})
                          .entries
                          .map((e) => _stateRow(e.key, e.value?.toString() ?? '—')),
                      _stateRow('Timestamp', latest['timestamp']?.toString() ?? '—'),
                    ],
                  ),
                ),
              );
            },
            orElse: () => const SizedBox.shrink(),
          ),
        ],
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
      child: Row(
        children: [
          Expanded(child: Text(key,
              style: const TextStyle(color: Color(0xFF64748B), fontSize: 12))),
          Text(value,
              style: const TextStyle(color: Colors.white, fontSize: 12,
                  fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }

  Widget _buildHistoryChart(Map<String, dynamic> data) {
    final history = (data['history'] as List? ?? [])
        .cast<Map<String, dynamic>>();
    if (history.isEmpty) {
      return const Center(child: Text('No history data',
          style: TextStyle(color: Color(0xFF64748B))));
    }

    // Try to find a numeric value to plot
    final reversed = history.reversed.toList();
    String? plotKey;
    for (final key in ['power_w', 'power', 'ph', 'pm2_5', 'co2', 'flow_rate',
                        'temperature', 'humidity', 'soc', 'voltage']) {
      if ((reversed.first['payload'] as Map? ?? {}).containsKey(key)) {
        plotKey = key;
        break;
      }
    }
    if (plotKey == null) {
      return const Center(child: Text('No numeric data to plot',
          style: TextStyle(color: Color(0xFF64748B))));
    }

    final spots = reversed.asMap().entries.map((e) {
      final v = (e.value['payload'] as Map? ?? {})[plotKey] ?? 0;
      return FlSpot(e.key.toDouble(), (v as num).toDouble());
    }).toList();

    return LineChart(LineChartData(
      gridData: FlGridData(
        show: true,
        getDrawingHorizontalLine: (_) =>
            FlLine(color: const Color(0xFF334155), strokeWidth: 1),
      ),
      borderData: FlBorderData(show: false),
      titlesData: FlTitlesData(
        leftTitles: AxisTitles(
          sideTitles: SideTitles(showTitles: true, reservedSize: 40,
            getTitlesWidget: (v, _) => Text('${v.toInt()}',
                style: const TextStyle(color: Color(0xFF64748B), fontSize: 9))),
        ),
        bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
      ),
      lineBarsData: [
        LineChartBarData(
          spots: spots,
          isCurved: true,
          color: _domainColor,
          barWidth: 2,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(
            show: true,
            color: _domainColor.withOpacity(0.08),
          ),
        ),
      ],
    ));
  }
}
