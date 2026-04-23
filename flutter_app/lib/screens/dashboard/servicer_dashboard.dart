import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/auth_provider.dart';
import '../../providers/dashboard_provider.dart';
import '../../core/api_client.dart';
import '../../widgets/actuator_toggle.dart';
import '../../widgets/node_list_tile.dart';

/// Servicer Dashboard — node health grid + node list + actuator drawer.
/// Map is temporarily replaced with a Zone Health Grid until flutter_map
/// package cache is repaired on this machine.
class ServicerDashboard extends ConsumerStatefulWidget {
  const ServicerDashboard({super.key});
  @override
  ConsumerState<ServicerDashboard> createState() => _ServicerDashboardState();
}

class _ServicerDashboardState extends ConsumerState<ServicerDashboard> {
  Map<String, dynamic>? _selectedNode;

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Servicer Console'),
          bottom: const TabBar(
            tabs: [
              Tab(text: 'Overview'),
              Tab(text: 'Active Tasks'),
              Tab(text: 'History'),
            ],
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: () {
                ref.invalidate(servicerDashboardProvider);
                ref.invalidate(myAssignmentsProvider);
              },
            ),
            IconButton(
              icon: const Icon(Icons.logout),
              onPressed: () => ref.read(authProvider.notifier).logout(),
            ),
          ],
        ),
        body: const TabBarView(
          children: [
            _OverviewTab(),
            _TasksTab(isActive: true),
            _TasksTab(isActive: false),
          ],
        ),
      ),
    );
  }
}

class _OverviewTab extends ConsumerStatefulWidget {
  const _OverviewTab();
  @override
  ConsumerState<_OverviewTab> createState() => _OverviewTabState();
}

class _OverviewTabState extends ConsumerState<_OverviewTab> {
  Map<String, dynamic>? _selectedNode;

  @override
  Widget build(BuildContext context) {
    final dashAsync = ref.watch(servicerDashboardProvider);
    
    return Scaffold(
      body: dashAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
            child: Text('Error: $e', style: const TextStyle(color: Colors.red))),
        data: (data) {
          final nodes = (data['nodes'] as List).cast<Map<String, dynamic>>();
          final summary = data['summary'] as Map<String, dynamic>;
          return Column(
            children: [
              _HealthSummaryBar(summary: summary),
              Expanded(
                flex: 3,
                child: _ZoneNodeGrid(
                  nodes: nodes,
                  onNodeTap: (node) => setState(() => _selectedNode = node),
                ),
              ),
              Expanded(
                flex: 2,
                child: ListView.builder(
                  itemCount: nodes.length,
                  itemBuilder: (_, i) => NodeListTile(
                    node: nodes[i],
                    onTap: () => setState(() => _selectedNode = nodes[i]),
                  ),
                ),
              ),
            ],
          );
        },
      ),
      endDrawer: _selectedNode == null
          ? null
          : _NodeDetailDrawer(
              node: _selectedNode!,
              onClose: () => setState(() => _selectedNode = null),
            ),
    );
  }
}

class _TasksTab extends ConsumerWidget {
  final bool isActive;
  const _TasksTab({required this.isActive});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assignmentsAsync = ref.watch(myAssignmentsProvider);

    return assignmentsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e', style: const TextStyle(color: Colors.red))),
      data: (allAssignments) {
        final tasks = allAssignments.where((a) {
          final isResolved = a['status'] == 'RESOLVED' || a['status'] == 'CLOSED';
          return isActive ? !isResolved : isResolved;
        }).toList();

        if (tasks.isEmpty) {
          return Center(
            child: Text(isActive ? 'No active tasks!' : 'No service history', 
              style: const TextStyle(color: Colors.grey)),
          );
        }

        return ListView.builder(
          itemCount: tasks.length,
          itemBuilder: (_, i) {
            final t = tasks[i];
            return Card(
              margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              color: const Color(0xFF1E293B),
              child: ListTile(
                title: Text('${t['node_id']} (${t['domain']})', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Zone: ${t['zone_id'] ?? 'Unknown'} | Status: ${t['status']}', style: const TextStyle(color: Colors.white70)),
                    if (t['notes'] != null) Text('Notes: ${t['notes']}', style: const TextStyle(color: Colors.white54)),
                  ],
                ),
                trailing: isActive ? ElevatedButton(
                  onPressed: () => _resolveDialog(context, ref, t['id']),
                  style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF4ADE80)),
                  child: const Text('Resolve', style: TextStyle(color: Colors.black)),
                ) : null,
              ),
            );
          },
        );
      },
    );
  }

  void _resolveDialog(BuildContext context, WidgetRef ref, String assignmentId) {
    final tc = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text('Resolve Assignment', style: TextStyle(color: Colors.white)),
        content: TextField(
          controller: tc,
          style: const TextStyle(color: Colors.white),
          decoration: const InputDecoration(
            labelText: 'Resolution Notes (Required)',
            labelStyle: TextStyle(color: Colors.white54),
          ),
          maxLines: 3,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel', style: TextStyle(color: Colors.white54)),
          ),
          ElevatedButton(
            onPressed: () async {
              if (tc.text.trim().isEmpty) return;
              try {
                await ApiClient.instance.put('/servicer/assignments/$assignmentId/resolve', data: {
                  'status': 'RESOLVED',
                  'notes': tc.text.trim(),
                });
                if (ctx.mounted) Navigator.pop(ctx);
                ref.invalidate(myAssignmentsProvider);
              } catch (e) {
                // Ignore error visual for now, let it pop
              }
            },
            child: const Text('Mark Resolved'),
          ),
        ],
      ),
    );
  }
}

// ── Health summary bar ───────────────────────────────────────────────────────

class _HealthSummaryBar extends StatelessWidget {
  final Map<String, dynamic> summary;
  const _HealthSummaryBar({required this.summary});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: const Color(0xFF1E293B),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _badge('Total',    '${summary['total']}',    Colors.white),
          _badge('Healthy',  '${summary['healthy']}',  const Color(0xFF4ADE80)),
          _badge('Degraded', '${summary['degraded']}', const Color(0xFFFBBF24)),
          _badge('Offline',  '${summary['offline']}',  const Color(0xFFEF4444)),
        ],
      ),
    );
  }

  Widget _badge(String label, String value, Color color) => Column(
    children: [
      Text(value, style: TextStyle(
          color: color, fontWeight: FontWeight.bold, fontSize: 20)),
      Text(label, style: const TextStyle(
          color: Color(0xFF94A3B8), fontSize: 11)),
    ],
  );
}

// ── Zone Node Grid ───────────────────────────────────────────────────────────
/// Groups nodes by their zone and renders a dot-grid per zone.
/// Tap a dot to open the node detail drawer.

class _ZoneNodeGrid extends StatelessWidget {
  final List<Map<String, dynamic>> nodes;
  final ValueChanged<Map<String, dynamic>> onNodeTap;
  const _ZoneNodeGrid({required this.nodes, required this.onNodeTap});

  Color _dotColor(String? health, String? state) {
    if (state == 'OFFLINE') return const Color(0xFFEF4444);
    if (health == 'DEGRADED') return const Color(0xFFFBBF24);
    return const Color(0xFF4ADE80);
  }

  @override
  Widget build(BuildContext context) {
    // Group nodes by zone
    final Map<String, List<Map<String, dynamic>>> byZone = {};
    for (final n in nodes) {
      final zone = (n['zone'] as String?) ?? 'Unknown';
      byZone.putIfAbsent(zone, () => []).add(n);
    }

    return ListView(
      padding: const EdgeInsets.all(12),
      children: byZone.entries.map((entry) {
        final zone = entry.key;
        final zoneNodes = entry.value;
        final healthy  = zoneNodes.where((n) => n['health'] == 'OK').length;
        final degraded = zoneNodes.where((n) => n['health'] == 'DEGRADED').length;
        final offline  = zoneNodes.where((n) => n['state']  == 'OFFLINE').length;

        return Card(
          margin: const EdgeInsets.only(bottom: 10),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Zone header
                Row(children: [
                  const Icon(Icons.location_city,
                      size: 16, color: Color(0xFF38BDF8)),
                  const SizedBox(width: 6),
                  Text(zone, style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 14)),
                  const Spacer(),
                  Text('${zoneNodes.length} nodes',
                      style: const TextStyle(
                          color: Color(0xFF64748B), fontSize: 11)),
                ]),
                const SizedBox(height: 4),
                // Status micro-summary
                Row(children: [
                  _pill('✅ $healthy OK',      const Color(0xFF166534)),
                  if (degraded > 0) _pill('⚠️ $degraded Degraded', const Color(0xFF78350F)),
                  if (offline  > 0) _pill('🔴 $offline Offline',   const Color(0xFF7F1D1D)),
                ]),
                const SizedBox(height: 10),
                // Dot grid — one dot per node
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: zoneNodes.map((n) {
                    final color = _dotColor(
                        n['health']?.toString(), n['state']?.toString());
                    return GestureDetector(
                      onTap: () => onNodeTap(n),
                      child: Tooltip(
                        message: '${n['node_id']} — ${n['node_type']}',
                        child: Container(
                          width: 20, height: 20,
                          decoration: BoxDecoration(
                            color: color,
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                  color: color.withOpacity(0.5),
                                  blurRadius: 6,
                                  spreadRadius: 1),
                            ],
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _pill(String label, Color bg) => Container(
    margin: const EdgeInsets.only(right: 6, bottom: 4),
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
    decoration: BoxDecoration(
        color: bg, borderRadius: BorderRadius.circular(12)),
    child: Text(label,
        style: const TextStyle(color: Colors.white, fontSize: 11)),
  );
}

// ── Node Detail Drawer ───────────────────────────────────────────────────────

class _NodeDetailDrawer extends ConsumerWidget {
  final Map<String, dynamic> node;
  final VoidCallback onClose;
  const _NodeDetailDrawer({required this.node, required this.onClose});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final nodeId = node['node_id'] as String;
    final isActuator = ['ac_unit', 'light', 'pump', 'valve']
        .any((t) => node['node_type']?.toString().contains(t) == true);

    return Drawer(
      backgroundColor: const Color(0xFF1E293B),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                    child: Text(nodeId,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 16))),
                IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: onClose),
              ]),
              const SizedBox(height: 12),
              _row('Type',      node['node_type']  ?? '-'),
              _row('Zone',      node['zone']        ?? '-'),
              _row('Health',    node['health']      ?? '-'),
              _row('State',     node['state']       ?? '-'),
              _row('Last seen', node['last_seen']?.toString().substring(0, 16) ?? '-'),
              const Divider(color: Color(0xFF334155), height: 30),
              if (isActuator) ...[
                const Text('Actuator Control',
                    style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                const SizedBox(height: 10),
                ActuatorToggle(
                    nodeId: nodeId, label: node['node_type'] ?? nodeId),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _row(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: Row(children: [
      SizedBox(
          width: 90,
          child: Text(label,
              style: const TextStyle(
                  color: Color(0xFF94A3B8), fontSize: 13))),
      Expanded(
          child: Text(value,
              style: const TextStyle(color: Colors.white, fontSize: 13))),
    ]),
  );
}
