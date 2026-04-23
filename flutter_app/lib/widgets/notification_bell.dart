import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/dashboard_provider.dart';
import '../core/api_client.dart';

/// Notification bell shown in AppBar — shows unread badge count.
/// Tapping navigates to NotificationPanel.
class NotificationBell extends ConsumerWidget {
  const NotificationBell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final countAsync = ref.watch(notificationCountProvider);

    return countAsync.when(
      loading: () => IconButton(
        icon: const Icon(Icons.notifications_outlined),
        onPressed: () => _openPanel(context),
      ),
      error: (_, __) => IconButton(
        icon: const Icon(Icons.notifications_outlined),
        onPressed: () => _openPanel(context),
      ),
      data: (count) => Stack(
        alignment: Alignment.center,
        children: [
          IconButton(
            icon: const Icon(Icons.notifications_outlined),
            onPressed: () => _openPanel(context),
          ),
          if (count > 0)
            Positioned(
              right: 6,
              top: 6,
              child: Container(
                padding: const EdgeInsets.all(3),
                decoration: const BoxDecoration(
                  color: Color(0xFFEF4444),
                  shape: BoxShape.circle,
                ),
                constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                child: Text(
                  count > 99 ? '99+' : '$count',
                  style: const TextStyle(color: Colors.white, fontSize: 9,
                      fontWeight: FontWeight.bold),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
        ],
      ),
    );
  }

  void _openPanel(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const NotificationPanel()),
    );
  }
}


/// Full-screen notification panel with unread/read tabs.
class NotificationPanel extends ConsumerStatefulWidget {
  const NotificationPanel({super.key});
  @override
  ConsumerState<NotificationPanel> createState() => _NotificationPanelState();
}

class _NotificationPanelState extends ConsumerState<NotificationPanel>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  Future<void> _ackAlert(String alertId) async {
    try {
      await ApiClient.instance.put('/alerts/$alertId/acknowledge', data: {});
      ref.invalidate(myAlertsProvider);
      ref.invalidate(myAlertsAllProvider);
      ref.invalidate(notificationCountProvider);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: const Color(0xFF7F1D1D)),
        );
      }
    }
  }

  Future<void> _ackAll(List<Map<String, dynamic>> alerts) async {
    for (final a in alerts) {
      await _ackAlert(a['id'] as String);
    }
  }

  @override
  Widget build(BuildContext context) {
    final unreadAsync = ref.watch(myAlertsProvider);
    final allAsync   = ref.watch(myAlertsAllProvider);

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        title: const Text('Notifications'),
        backgroundColor: const Color(0xFF1E293B),
        bottom: TabBar(
          controller: _tabs,
          labelColor: const Color(0xFF38BDF8),
          unselectedLabelColor: const Color(0xFF64748B),
          indicatorColor: const Color(0xFF38BDF8),
          tabs: const [
            Tab(icon: Icon(Icons.circle_notifications), text: 'Unread'),
            Tab(icon: Icon(Icons.history), text: 'All'),
          ],
        ),
        actions: [
          unreadAsync.maybeWhen(
            data: (alerts) => alerts.isNotEmpty
                ? TextButton(
                    onPressed: () => _ackAll(alerts),
                    child: const Text('Mark all read',
                        style: TextStyle(color: Color(0xFF38BDF8))),
                  )
                : const SizedBox.shrink(),
            orElse: () => const SizedBox.shrink(),
          ),
        ],
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          // Unread tab
          unreadAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('$e', style: const TextStyle(color: Colors.red))),
            data: (alerts) => alerts.isEmpty
                ? const Center(
                    child: Text('🎉 All caught up!',
                        style: TextStyle(color: Color(0xFF64748B), fontSize: 16)),
                  )
                : _AlertList(alerts: alerts, onAck: _ackAlert),
          ),
          // All alerts tab
          allAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('$e', style: const TextStyle(color: Colors.red))),
            data: (alerts) => alerts.isEmpty
                ? const Center(child: Text('No alerts yet',
                    style: TextStyle(color: Color(0xFF64748B))))
                : _AlertList(alerts: alerts, onAck: _ackAlert, showAll: true),
          ),
        ],
      ),
    );
  }
}


class _AlertList extends StatelessWidget {
  final List<Map<String, dynamic>> alerts;
  final Future<void> Function(String) onAck;
  final bool showAll;

  const _AlertList({required this.alerts, required this.onAck, this.showAll = false});

  Color _severityColor(String? severity) {
    switch (severity) {
      case 'CRITICAL': return const Color(0xFFEF4444);
      case 'WARNING':  return const Color(0xFFF59E0B);
      default:         return const Color(0xFF38BDF8);
    }
  }

  IconData _severityIcon(String? severity) {
    switch (severity) {
      case 'CRITICAL': return Icons.warning_amber_rounded;
      case 'WARNING':  return Icons.info_outline;
      default:         return Icons.notifications_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: alerts.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (_, i) {
        final a = alerts[i];
        final acked = a['acknowledged'] == true;
        final color = _severityColor(a['severity'] as String?);
        return AnimatedOpacity(
          opacity: acked && showAll ? 0.5 : 1.0,
          duration: const Duration(milliseconds: 300),
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF1E293B),
              borderRadius: BorderRadius.circular(12),
              border: Border(left: BorderSide(color: color, width: 4)),
            ),
            child: ListTile(
              leading: Icon(_severityIcon(a['severity'] as String?), color: color),
              title: Text(
                a['message'] as String? ?? '',
                style: TextStyle(
                  color: acked ? const Color(0xFF64748B) : Colors.white,
                  fontWeight: acked ? FontWeight.normal : FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 2),
                  Text(
                    [
                      if (a['domain'] != null) '📡 ${a['domain']}',
                      if (a['zone_id'] != null) '📍 ${a['zone_id']}',
                      if (a['node_id'] != null) '🔌 ${a['node_id']}',
                    ].join('  '),
                    style: const TextStyle(color: Color(0xFF64748B), fontSize: 11),
                  ),
                  Text(
                    a['created_at'] as String? ?? '',
                    style: const TextStyle(color: Color(0xFF475569), fontSize: 10),
                  ),
                ],
              ),
              trailing: acked
                  ? const Icon(Icons.check_circle_outline, color: Color(0xFF4ADE80), size: 18)
                  : IconButton(
                      icon: const Icon(Icons.done, color: Color(0xFF38BDF8), size: 18),
                      onPressed: () => onAck(a['id'] as String),
                      tooltip: 'Mark as read',
                    ),
            ),
          ),
        );
      },
    );
  }
}
