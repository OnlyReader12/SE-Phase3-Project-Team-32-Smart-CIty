import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/auth_provider.dart';
import '../../providers/dashboard_provider.dart';
import '../../widgets/kpi_card.dart';
import '../../widgets/alert_feed.dart';
import '../../widgets/subscription_panel.dart';
import '../../widgets/actuator_toggle.dart';
import '../../widgets/notification_bell.dart';
import '../node_detail_screen.dart';

/// Resident Dashboard — Live node list + zone-scoped alerts + subscription manager.
class ResidentDashboard extends ConsumerWidget {
  const ResidentDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashAsync     = ref.watch(residentDashboardProvider);
    final myNodesAsync  = ref.watch(myNodesProvider);

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text('My Dashboard'),
        actions: [
          const NotificationBell(),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ref.invalidate(residentDashboardProvider);
              ref.invalidate(myNodesProvider);
              ref.invalidate(notificationCountProvider);
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(residentDashboardProvider);
          ref.invalidate(myNodesProvider);
          ref.invalidate(notificationCountProvider);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // ── Subscription zone picker ──────────────────────────────
            const SubscriptionPanel(),
            const SizedBox(height: 20),

            // ── Summary cards ─────────────────────────────────────────
            Text('Live Summary',
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(color: Colors.white, fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            dashAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error:   (e, _) => _errorCard('Dashboard unavailable', e.toString()),
              data:    (data) => _buildSummaryCards(data['summary'] ?? {}),
            ),
            const SizedBox(height: 24),

            // ── My Nodes ──────────────────────────────────────────────
            Text('🔌 My Nodes',
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(color: Colors.white, fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            myNodesAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error:   (e, _) => _errorCard('Nodes unavailable', e.toString()),
              data:    (nodes) => nodes.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.all(16),
                      child: Text(
                        'No nodes yet. Subscribe to zones above to see your nodes.',
                        style: TextStyle(color: Color(0xFF64748B)),
                        textAlign: TextAlign.center,
                      ),
                    )
                  : _buildNodeList(context, nodes),
            ),
            const SizedBox(height: 24),

            // ── Alerts ────────────────────────────────────────────────
            Text('🔔 Local Alerts',
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(color: Colors.white, fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            Consumer(builder: (ctx, ref, _) {
              final alertAsync = ref.watch(myAlertsProvider);
              return alertAsync.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error:   (e, _) => _errorCard('Alerts unavailable', e.toString()),
                data:    (alerts) => AlertFeed(alerts: alerts),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryCards(Map<String, dynamic> summary) {
    return Row(
      children: [
        if (summary.containsKey('energy'))
          Expanded(child: KpiCard(
            icon: Icons.bolt, label: 'Energy',
            value: '${summary['energy']['avg_power_w']} W',
            subtitle: '${summary['energy']['active_nodes']} nodes',
            color: const Color(0xFFFBBF24),
          )),
        if (summary.containsKey('water')) ...[
          const SizedBox(width: 10),
          Expanded(child: KpiCard(
            icon: Icons.water_drop, label: 'Water',
            value: 'pH ${summary['water']['ph_avg']}',
            subtitle: '${summary['water']['node_count']} nodes',
            color: const Color(0xFF38BDF8),
          )),
        ],
        if (summary.containsKey('air')) ...[
          const SizedBox(width: 10),
          Expanded(child: KpiCard(
            icon: Icons.air, label: 'Air',
            value: 'PM2.5 ${summary['air']['aqi_avg']}',
            subtitle: 'CO₂ ${summary['air']['co2_avg']} ppm',
            color: const Color(0xFF4ADE80),
          )),
        ],
      ],
    );
  }

  Widget _buildNodeList(BuildContext context, List<Map<String, dynamic>> nodes) {
    return Column(
      children: nodes.map((node) {
        final health = node['health'] as String? ?? 'UNKNOWN';
        final healthColor = health == 'OK'
            ? const Color(0xFF4ADE80)
            : health == 'DEGRADED'
                ? const Color(0xFFF59E0B)
                : const Color(0xFFEF4444);

        return Card(
          color: const Color(0xFF1E293B),
          margin: const EdgeInsets.only(bottom: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          child: ListTile(
            leading: Container(
              width: 10, height: 10,
              decoration: BoxDecoration(color: healthColor, shape: BoxShape.circle),
            ),
            title: Text(node['node_id'] as String? ?? '',
                style: const TextStyle(color: Colors.white, fontSize: 13,
                    fontWeight: FontWeight.w600)),
            subtitle: Text(
              '${node['zone']}  •  ${node['domain']}  •  ${node['state'] ?? ''}',
              style: const TextStyle(color: Color(0xFF64748B), fontSize: 11),
            ),
            trailing: const Icon(Icons.chevron_right, color: Color(0xFF475569)),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => NodeDetailScreen(
                nodeId:   node['node_id'] as String,
                nodeType: node['node_type'] as String? ?? '',
                zone:     node['zone'] as String? ?? '',
                domain:   node['domain'] as String? ?? '',
                health:   node['health'] as String?,
              ),
            )),
          ),
        );
      }).toList(),
    );
  }

  Widget _errorCard(String title, String detail) => Card(
    color: const Color(0xFF7F1D1D),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        Text(detail, style: const TextStyle(color: Color(0xFFFCA5A5), fontSize: 12)),
      ]),
    ),
  );
}
