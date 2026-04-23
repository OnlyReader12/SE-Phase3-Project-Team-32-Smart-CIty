import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/auth_provider.dart';
import '../../providers/dashboard_provider.dart';
import '../../widgets/kpi_card.dart';
import '../../widgets/notification_bell.dart';
import '../../widgets/rule_charts.dart';

/// Analyst Dashboard — team-scoped: Energy analyst sees Energy only,
/// EHS analyst sees Water + Air.
class AnalystDashboard extends ConsumerStatefulWidget {
  const AnalystDashboard({super.key});
  @override
  ConsumerState<AnalystDashboard> createState() => _AnalystDashboardState();
}

class _AnalystDashboardState extends ConsumerState<AnalystDashboard>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  List<String> _domains(String? team) =>
      team == 'EHS' ? ['water', 'air'] : ['energy'];

  @override
  void initState() {
    super.initState();
    final team = ref.read(authProvider).team;
    _tabs = TabController(length: _domains(team).length, vsync: this);
  }

  @override
  Widget build(BuildContext context) {
    final dashAsync = ref.watch(analystDashboardProvider);
    final team      = ref.watch(authProvider).team;
    final domains   = _domains(team);

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text('Analytics'),
        bottom: domains.length > 1
            ? TabBar(
                controller: _tabs,
                labelColor: const Color(0xFF38BDF8),
                unselectedLabelColor: const Color(0xFF64748B),
                indicatorColor: const Color(0xFF38BDF8),
                tabs: [
                  if (domains.contains('water'))
                    const Tab(icon: Icon(Icons.water_drop), text: 'Water'),
                  if (domains.contains('air'))
                    const Tab(icon: Icon(Icons.air), text: 'Air'),
                ],
              )
            : null,
        actions: [
          const NotificationBell(),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(analystDashboardProvider),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: dashAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e',
            style: const TextStyle(color: Colors.red))),
        data: (data) {
          if (domains.length == 1) {
            return DomainView(domain: domains[0], data: data[domains[0]] ?? {});
          }
          return TabBarView(
            controller: _tabs,
            children: domains.map((d) =>
                DomainView(domain: d, data: data[d] ?? {})).toList(),
          );
        },
      ),
    );
  }
}


/// DomainView — KPI cards + chart for one domain.
/// Used by both AnalystDashboard and _TeamScopedAnalytics in ManagerDashboard.
class DomainView extends StatelessWidget {
  final String domain;
  final Map<String, dynamic> data;
  const DomainView({required this.domain, required this.data, super.key});

  @override
  Widget build(BuildContext context) {
    // prediction_3_readings: fallback to avg_power_w if empty for visual
    final raw = data['prediction_3_readings'] as List?;
    List<double> prediction = raw != null
        ? raw.map((v) => (v as num).toDouble()).toList()
        : [];

    // If prediction is empty but we have node_count, generate mock
    // placeholder so the chart always shows something meaningful
    if (prediction.isEmpty) {
      final avg = _avgValue();
      if (avg > 0) {
        prediction = List.generate(5, (i) => avg * (0.9 + i * 0.05));
      }
    }

    final avg   = _avgValue();
    final peak  = (data['peak_power_w'] as num?)?.toDouble() ?? avg;
    final faults = (data['fault_count'] ?? data['contamination_events'] ?? 0) as int;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildKpiRow(),
        const SizedBox(height: 16),

        if ((data['node_count'] ?? data['active_nodes'] ?? 0) > 0)
          _infoBanner('${data['node_count'] ?? data['active_nodes']} nodes active'),

        const SizedBox(height: 16),

        // ── Rule-Specific Charts ──────────────────────────────────────
        if (domain == 'energy') ...[
          PowerBalanceChart(
              avgPowerW: avg, peakPowerW: peak, prediction: prediction),
          const SizedBox(height: 12),
          SolarEfficiencyChart(avgPowerW: avg, peakPowerW: peak),
          const SizedBox(height: 12),
          ConsumptionAnomalyChart(prediction: prediction, faultCount: faults),
          const SizedBox(height: 12),
          GridStabilityChart(avgPowerW: avg, faultCount: faults),
          const SizedBox(height: 12),
          DeviceScheduleChart(faultCount: faults),
        ],

        if (domain == 'water') ...[
          WaterQualityChart(
            phAvg: (data['ph_avg'] as num?)?.toDouble() ?? 7.0,
            events: faults,
            prediction: prediction,
          ),
          const SizedBox(height: 12),
          WaterSafetyChart(events: faults),
          const SizedBox(height: 12),
          EquipmentHealthChart(events: faults),
        ],

        if (domain == 'air') ...[
          AirQualityRadarChart(
            pm25: (data['pm25_avg'] as num?)?.toDouble() ?? 15.0,
            co2:  (data['co2_avg']  as num?)?.toDouble() ?? 500.0,
          ),
          const SizedBox(height: 12),
          IndoorComfortChart(
            pm25: (data['pm25_avg'] as num?)?.toDouble() ?? 15.0,
            co2:  (data['co2_avg']  as num?)?.toDouble() ?? 500.0,
          ),
        ],

        // ── Anomaly Banner ────────────────────────────────────────────
        if (faults > 0) ...[
          const SizedBox(height: 16),
          Card(
            color: const Color(0xFF7C2D12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(children: [
                const Icon(Icons.warning_amber, color: Colors.orange),
                const SizedBox(width: 10),
                Text('$faults anomalies / contamination events detected',
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold)),
              ]),
            ),
          ),
        ],
        const SizedBox(height: 24),
      ],
    );
  }

  double _avgValue() {
    if (domain == 'energy') return (data['avg_power_w'] as num?)?.toDouble() ?? 0;
    if (domain == 'water')  return (data['ph_avg'] as num?)?.toDouble() ?? 0;
    if (domain == 'air')    return (data['pm25_avg'] as num?)?.toDouble() ?? 0;
    return 0;
  }

  Widget _infoBanner(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFF0369A1).withOpacity(0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF38BDF8).withOpacity(0.3)),
      ),
      child: Row(children: [
        const Icon(Icons.device_hub, color: Color(0xFF38BDF8), size: 14),
        const SizedBox(width: 6),
        Text(text, style: const TextStyle(color: Color(0xFF38BDF8), fontSize: 12)),
      ]),
    );
  }

  Widget _buildKpiRow() {
    if (domain == 'energy') {
      return Row(children: [
        Expanded(child: KpiCard(
            icon: Icons.bolt, label: 'Avg Power',
            value: '${data['avg_power_w'] ?? 0} W',
            color: const Color(0xFFFBBF24))),
        const SizedBox(width: 10),
        Expanded(child: KpiCard(
            icon: Icons.trending_up, label: 'Peak',
            value: '${data['peak_power_w'] ?? 0} W',
            color: const Color(0xFFF97316))),
        const SizedBox(width: 10),
        Expanded(child: KpiCard(
            icon: Icons.error_outline, label: 'Faults',
            value: '${data['fault_count'] ?? 0}',
            color: const Color(0xFFEF4444))),
      ]);
    } else if (domain == 'water') {
      return Row(children: [
        Expanded(child: KpiCard(
            icon: Icons.science, label: 'pH Avg',
            value: '${data['ph_avg'] ?? 0}',
            color: const Color(0xFF38BDF8))),
        const SizedBox(width: 10),
        Expanded(child: KpiCard(
            icon: Icons.warning, label: 'Events',
            value: '${data['contamination_events'] ?? 0}',
            color: const Color(0xFFEF4444))),
      ]);
    } else {
      return Row(children: [
        Expanded(child: KpiCard(
            icon: Icons.cloud, label: 'PM2.5',
            value: '${data['pm25_avg'] ?? 0} µg',
            color: const Color(0xFF4ADE80))),
        const SizedBox(width: 10),
        Expanded(child: KpiCard(
            icon: Icons.co2, label: 'CO₂',
            value: '${data['co2_avg'] ?? 0} ppm',
            color: const Color(0xFF818CF8))),
      ]);
    }
  }
}
