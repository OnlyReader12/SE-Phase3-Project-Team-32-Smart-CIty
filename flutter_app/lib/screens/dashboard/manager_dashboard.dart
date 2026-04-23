import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/auth_provider.dart';
import '../../providers/dashboard_provider.dart';
import '../../core/api_client.dart';
import '../../widgets/notification_bell.dart';
import '../node_detail_screen.dart';
import 'analyst_dashboard.dart';

// ── Manager Dashboard ──────────────────────────────────────────────────────
// 4 tabs: Analytics | Health Map | Team | Nodes
// All tabs are TEAM-SCOPED: Energy team sees only energy; EHS sees water+air.
class ManagerDashboard extends ConsumerStatefulWidget {
  const ManagerDashboard({super.key});
  @override
  ConsumerState<ManagerDashboard> createState() => _ManagerDashboardState();
}

class _ManagerDashboardState extends ConsumerState<ManagerDashboard>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 4, vsync: this);
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final team = authState.team ?? 'ENERGY';

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: Text('${team == 'EHS' ? 'EHS' : 'Energy'} Manager Console'),
        bottom: TabBar(
          controller: _tabs,
          labelColor: const Color(0xFF38BDF8),
          unselectedLabelColor: const Color(0xFF64748B),
          indicatorColor: const Color(0xFF38BDF8),
          isScrollable: true,
          tabs: const [
            Tab(icon: Icon(Icons.analytics),      text: 'Analytics'),
            Tab(icon: Icon(Icons.monitor_heart),  text: 'Health Map'),
            Tab(icon: Icon(Icons.people_outline), text: 'Team'),
            Tab(icon: Icon(Icons.device_hub),     text: 'Nodes'),
          ],
        ),
        actions: [
          const NotificationBell(),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _TeamScopedAnalytics(team: team),
          _HealthMapTab(team: team),
          _TeamPanel(team: team),
          _NodeBrowserPanel(team: team),
        ],
      ),
    );
  }
}


// ── Analytics tab — shows only domains for this team ──────────────────────
class _TeamScopedAnalytics extends ConsumerStatefulWidget {
  final String team;
  const _TeamScopedAnalytics({required this.team});

  @override
  ConsumerState<_TeamScopedAnalytics> createState() => _TeamScopedAnalyticsState();
}

class _TeamScopedAnalyticsState extends ConsumerState<_TeamScopedAnalytics>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  List<String> get _domains =>
      widget.team == 'EHS' ? ['water', 'air'] : ['energy'];

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: _domains.length, vsync: this);
  }

  @override
  Widget build(BuildContext context) {
    final dashAsync = ref.watch(analystDashboardProvider);

    return Column(children: [
      if (_domains.length > 1)
        TabBar(
          controller: _tabs,
          labelColor: const Color(0xFF38BDF8),
          unselectedLabelColor: const Color(0xFF64748B),
          indicatorColor: const Color(0xFF38BDF8),
          tabs: [
            if (_domains.contains('water'))
              const Tab(icon: Icon(Icons.water_drop), text: 'Water'),
            if (_domains.contains('air'))
              const Tab(icon: Icon(Icons.air), text: 'Air'),
          ],
        ),
      Expanded(
        child: dashAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('$e',
              style: const TextStyle(color: Colors.red))),
          data: (data) {
            if (_domains.length == 1) {
              return DomainView(domain: _domains[0], data: data[_domains[0]] ?? {});
            }
            return TabBarView(
              controller: _tabs,
              children: _domains.map((d) =>
                  DomainView(domain: d, data: data[d] ?? {})).toList(),
            );
          },
        ),
      ),
    ]);
  }
}


// ── Health Map tab ─────────────────────────────────────────────────────────
class _HealthMapTab extends ConsumerWidget {
  final String team;
  const _HealthMapTab({required this.team});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final nodesAsync = ref.watch(managerNodesProvider);

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: nodesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Column(
          mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.cloud_off, color: Color(0xFF64748B), size: 48),
            const SizedBox(height: 12),
            Text('Could not load node health\n$e',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF64748B))),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
              onPressed: () => ref.invalidate(managerNodesProvider),
            ),
          ],
        )),
        data: (nodes) {
          if (nodes.isEmpty) {
            return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.device_hub, color: Color(0xFF334155), size: 64),
              const SizedBox(height: 12),
              const Text('No nodes online yet.\nMake sure the Simulator and Middleware are running.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Color(0xFF64748B))),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                icon: const Icon(Icons.refresh),
                label: const Text('Refresh'),
                onPressed: () => ref.invalidate(managerNodesProvider),
              ),
            ]));
          }

          final healthy  = nodes.where((n) => n['health'] == 'OK').length;
          final degraded = nodes.where((n) => n['health'] == 'DEGRADED').length;
          final offline  = nodes.where((n) => n['health'] != 'OK' && n['health'] != 'DEGRADED').length;

          return Column(children: [
            // Header stats row
            Container(
              color: const Color(0xFF1E293B),
              padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
              child: Row(children: [
                _statBadge('Node Health', '', Colors.white),
                const Spacer(),
                _statBadge('${nodes.length}', 'Total', const Color(0xFF94A3B8)),
                const SizedBox(width: 16),
                _statBadge('$healthy', 'Healthy', const Color(0xFF4ADE80)),
                const SizedBox(width: 16),
                _statBadge('$degraded', 'Degraded', const Color(0xFFF59E0B)),
                const SizedBox(width: 16),
                _statBadge('$offline', 'Offline', const Color(0xFFEF4444)),
                const SizedBox(width: 8),
                IconButton(
                  icon: const Icon(Icons.refresh, color: Color(0xFF38BDF8), size: 18),
                  onPressed: () => ref.invalidate(managerNodesProvider),
                ),
              ]),
            ),

            // Zone grouping
            Expanded(child: _buildZoneGroups(context, ref, nodes)),
          ]);
        },
      ),
    );
  }

  Widget _buildZoneGroups(BuildContext context, WidgetRef ref,
      List<Map<String, dynamic>> nodes) {
    // Group nodes by zone
    final Map<String, List<Map<String, dynamic>>> byZone = {};
    for (final n in nodes) {
      final zone = n['zone'] as String? ?? 'Unknown';
      byZone.putIfAbsent(zone, () => []).add(n);
    }

    return ListView(
      padding: const EdgeInsets.all(12),
      children: byZone.entries.map((entry) {
        final zoneNodes = entry.value;
        final okCount = zoneNodes.where((n) => n['health'] == 'OK').length;
        final zoneColor = okCount == zoneNodes.length
            ? const Color(0xFF4ADE80)
            : okCount == 0
                ? const Color(0xFFEF4444)
                : const Color(0xFFF59E0B);

        return Card(
          color: const Color(0xFF1E293B),
          margin: const EdgeInsets.only(bottom: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          child: ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
            leading: Container(
              width: 10, height: 10,
              decoration: BoxDecoration(color: zoneColor, shape: BoxShape.circle),
            ),
            title: Text(entry.key,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            subtitle: Text('$okCount/${zoneNodes.length} healthy',
                style: TextStyle(color: zoneColor, fontSize: 11)),
            children: zoneNodes.map((n) => _nodeRow(context, n)).toList(),
          ),
        );
      }).toList(),
    );
  }

  Widget _nodeRow(BuildContext context, Map<String, dynamic> n) {
    final health = n['health'] as String? ?? 'UNKNOWN';
    final healthColor = health == 'OK'
        ? const Color(0xFF4ADE80)
        : health == 'DEGRADED'
            ? const Color(0xFFF59E0B)
            : const Color(0xFFEF4444);

    return ListTile(
      dense: true,
      leading: Container(
        width: 8, height: 8,
        decoration: BoxDecoration(color: healthColor, shape: BoxShape.circle),
      ),
      title: Text(n['node_id'] as String? ?? '',
          style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 12)),
      subtitle: Text('${n['domain']}  •  ${n['state'] ?? '—'}',
          style: const TextStyle(color: Color(0xFF64748B), fontSize: 11)),
      trailing: Chip(
        label: Text(health, style: TextStyle(fontSize: 9, color: healthColor)),
        backgroundColor: healthColor.withOpacity(0.1),
        side: BorderSide(color: healthColor.withOpacity(0.3)),
        padding: EdgeInsets.zero,
      ),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => NodeDetailScreen(
          nodeId:   n['node_id'] as String,
          nodeType: n['node_type'] as String? ?? '',
          zone:     n['zone'] as String? ?? '',
          domain:   n['domain'] as String? ?? '',
          health:   health,
        ),
      )),
    );
  }

  Widget _statBadge(String value, String label, Color color) {
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Text(value,
          style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 18)),
      if (label.isNotEmpty)
        Text(label, style: const TextStyle(color: Color(0xFF64748B), fontSize: 10)),
    ]);
  }
}


// ── Team Panel ──────────────────────────────────────────────────────────────
class _TeamPanel extends ConsumerStatefulWidget {
  final String team;
  const _TeamPanel({required this.team});
  @override
  ConsumerState<_TeamPanel> createState() => _TeamPanelState();
}

class _TeamPanelState extends ConsumerState<_TeamPanel> {
  @override
  Widget build(BuildContext context) {
    final teamAsync = ref.watch(managerTeamProvider);

    return teamAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('$e',
          style: const TextStyle(color: Colors.red))),
      data: (data) {
        final members = (data['team'] as List? ?? [])
            .cast<Map<String, dynamic>>();
        return Scaffold(
          backgroundColor: Colors.transparent,
          floatingActionButton: FloatingActionButton.extended(
            icon: const Icon(Icons.person_add),
            label: const Text('Add Member'),
            backgroundColor: const Color(0xFF0369A1),
            onPressed: () => _showAddMemberDialog(context),
          ),
          body: members.isEmpty
              ? const Center(child: Text('No team members yet.',
                  style: TextStyle(color: Color(0xFF64748B))))
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: members.length,
                  itemBuilder: (_, i) => _MemberCard(
                    member: members[i],
                    onAssign: members[i]['role'] == 'SERVICER'
                        ? () => _showAssignNodeDialog(context, members[i])
                        : null,
                  ),
                ),
        );
      },
    );
  }

  void _showAddMemberDialog(BuildContext context) {
    final emailCtrl = TextEditingController();
    final nameCtrl  = TextEditingController();
    final passCtrl  = TextEditingController();
    String selectedRole = 'SERVICER';

    showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          backgroundColor: const Color(0xFF1E293B),
          title: const Text('Add Team Member',
              style: TextStyle(color: Colors.white)),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            _field(nameCtrl, 'Full Name'),
            const SizedBox(height: 10),
            _field(emailCtrl, 'Email'),
            const SizedBox(height: 10),
            _field(passCtrl, 'Temp Password', obscure: true),
            const SizedBox(height: 10),
            DropdownButtonFormField<String>(
              value: selectedRole,
              dropdownColor: const Color(0xFF1E293B),
              style: const TextStyle(color: Colors.white),
              items: const [
                DropdownMenuItem(value: 'SERVICER', child: Text('Technician')),
                DropdownMenuItem(value: 'ANALYST',  child: Text('Analyst')),
              ],
              onChanged: (v) => setS(() => selectedRole = v!),
              decoration: const InputDecoration(labelText: 'Role',
                  labelStyle: TextStyle(color: Color(0xFF94A3B8))),
            ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx),
                child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () async {
                try {
                  await ApiClient.instance.post('/manager/create-user', data: {
                    'email': emailCtrl.text,
                    'full_name': nameCtrl.text,
                    'password': passCtrl.text,
                    'role': selectedRole,
                  });
                  if (ctx.mounted) {
                    Navigator.pop(ctx);
                    ref.invalidate(managerTeamProvider); // refresh list
                  }
                } catch (e) {
                  if (ctx.mounted) ScaffoldMessenger.of(ctx).showSnackBar(
                      SnackBar(content: Text('Error: $e')));
                }
              },
              child: const Text('Create'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showAssignNodeDialog(
      BuildContext context, Map<String, dynamic> servicer) async {
    List<Map<String, dynamic>> nodes = [];
    try {
      final resp = await ApiClient.instance.get('/manager/nodes');
      nodes = (resp.data['nodes'] as List).cast<Map<String, dynamic>>();
    } catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not load nodes: $e')));
      return;
    }
    if (!context.mounted) return;

    String? selectedNodeId;
    final notesCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          backgroundColor: const Color(0xFF1E293B),
          title: Text('Assign Node to ${servicer['full_name']}',
              style: const TextStyle(color: Colors.white, fontSize: 15)),
          content: SingleChildScrollView(child: Column(
            mainAxisSize: MainAxisSize.min, children: [
              DropdownButtonFormField<String>(
                value: selectedNodeId,
                dropdownColor: const Color(0xFF1E293B),
                style: const TextStyle(color: Colors.white, fontSize: 12),
                hint: const Text('Select a node…',
                    style: TextStyle(color: Color(0xFF64748B))),
                items: nodes.map((n) => DropdownMenuItem(
                  value: n['node_id'] as String,
                  child: Text(
                    '${n['node_id']} (${n['zone']})',
                    style: const TextStyle(fontSize: 11),
                    overflow: TextOverflow.ellipsis,
                  ),
                )).toList(),
                onChanged: (v) => setS(() => selectedNodeId = v),
                decoration: const InputDecoration(labelText: 'Node',
                    labelStyle: TextStyle(color: Color(0xFF94A3B8))),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: notesCtrl,
                style: const TextStyle(color: Colors.white, fontSize: 13),
                decoration: const InputDecoration(
                  labelText: 'Notes (optional)',
                  labelStyle: TextStyle(color: Color(0xFF94A3B8)),
                ),
                maxLines: 2,
              ),
            ],
          )),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx),
                child: const Text('Cancel')),
            ElevatedButton(
              onPressed: selectedNodeId == null ? null : () async {
                final node = nodes.firstWhere(
                    (n) => n['node_id'] == selectedNodeId);
                try {
                  await ApiClient.instance.post('/manager/assignments', data: {
                    'servicer_id': servicer['user_id'],
                    'node_id':     selectedNodeId,
                    'domain':      node['domain'],
                    'zone_id':     node['zone'],
                    'notes':       notesCtrl.text.isEmpty ? null : notesCtrl.text,
                  });
                  if (ctx.mounted) {
                    Navigator.pop(ctx);
                    ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Assignment created ✓'),
                            backgroundColor: Color(0xFF166534)));
                  }
                } catch (e) {
                  if (ctx.mounted) ScaffoldMessenger.of(ctx).showSnackBar(
                      SnackBar(content: Text('Error: $e')));
                }
              },
              child: const Text('Assign'),
            ),
          ],
        ),
      ),
    );
  }

  TextField _field(TextEditingController c, String label,
      {bool obscure = false}) {
    return TextField(
      controller: c,
      obscureText: obscure,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: Color(0xFF94A3B8)),
      ),
    );
  }
}


// ── Node Browser panel ──────────────────────────────────────────────────────
class _NodeBrowserPanel extends ConsumerWidget {
  final String team;
  const _NodeBrowserPanel({required this.team});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final nodesAsync = ref.watch(managerNodesProvider);

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: nodesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('$e',
            style: const TextStyle(color: Colors.red))),
        data: (nodes) {
          if (nodes.isEmpty) {
            return const Center(child: Text('No nodes online for your team.',
                style: TextStyle(color: Color(0xFF64748B))));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: nodes.length,
            itemBuilder: (_, i) {
              final n = nodes[i];
              final health = n['health'] as String? ?? 'UNKNOWN';
              final healthColor = health == 'OK'
                  ? const Color(0xFF4ADE80)
                  : health == 'DEGRADED'
                      ? const Color(0xFFF59E0B)
                      : const Color(0xFFEF4444);

              return Card(
                color: const Color(0xFF1E293B),
                margin: const EdgeInsets.only(bottom: 8),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
                child: ListTile(
                  leading: Container(
                    width: 10, height: 10,
                    decoration: BoxDecoration(
                        color: healthColor, shape: BoxShape.circle),
                  ),
                  title: Text(n['node_id'] as String? ?? '',
                      style: const TextStyle(color: Colors.white,
                          fontSize: 13, fontWeight: FontWeight.w600)),
                  subtitle: Text(
                    '${n['zone']}  •  ${n['domain']}  •  ${n['state'] ?? '—'}',
                    style: const TextStyle(
                        color: Color(0xFF64748B), fontSize: 11),
                  ),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    Chip(
                      label: Text(health, style: const TextStyle(
                          fontSize: 10, color: Colors.white)),
                      backgroundColor: healthColor.withOpacity(0.2),
                      side: BorderSide(color: healthColor.withOpacity(0.5)),
                      padding: EdgeInsets.zero,
                    ),
                    const Icon(Icons.chevron_right,
                        color: Color(0xFF475569)),
                  ]),
                  onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => NodeDetailScreen(
                        nodeId:   n['node_id'] as String,
                        nodeType: n['node_type'] as String? ?? '',
                        zone:     n['zone'] as String? ?? '',
                        domain:   n['domain'] as String? ?? '',
                        health:   health,
                      ))),
                ),
              );
            },
          );
        },
      ),
    );
  }
}


// ── Member card ─────────────────────────────────────────────────────────────
class _MemberCard extends StatelessWidget {
  final Map<String, dynamic> member;
  final VoidCallback? onAssign;
  const _MemberCard({required this.member, this.onAssign});

  @override
  Widget build(BuildContext context) {
    final assignments = (member['assignments'] as List? ?? [])
        .cast<Map<String, dynamic>>();

    return Card(
      color: const Color(0xFF1E293B),
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            CircleAvatar(
              backgroundColor: const Color(0xFF38BDF8),
              radius: 18,
              child: Text(
                (member['full_name'] as String? ?? '?')[0].toUpperCase(),
                style: const TextStyle(color: Color(0xFF0F172A),
                    fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(member['full_name'] as String? ?? '',
                  style: const TextStyle(color: Colors.white,
                      fontWeight: FontWeight.bold, fontSize: 13)),
              Text(member['email'] as String? ?? '',
                  style: const TextStyle(
                      color: Color(0xFF94A3B8), fontSize: 11)),
            ])),
            Chip(
              label: Text(member['role'] as String? ?? '',
                  style: const TextStyle(fontSize: 10, color: Colors.white)),
              backgroundColor: const Color(0xFF334155),
            ),
            if (onAssign != null) ...[
              const SizedBox(width: 6),
              IconButton(
                icon: const Icon(Icons.assignment_add,
                    color: Color(0xFF38BDF8), size: 20),
                tooltip: 'Assign Node',
                onPressed: onAssign,
              ),
            ],
          ]),
          if (assignments.isNotEmpty) ...[
            const SizedBox(height: 10),
            const Text('Assignments:',
                style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
            const SizedBox(height: 4),
            ...assignments.map((a) => Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Row(children: [
                Icon(Icons.circle, size: 6,
                    color: a['status'] == 'RESOLVED'
                        ? const Color(0xFF4ADE80)
                        : const Color(0xFF38BDF8)),
                const SizedBox(width: 6),
                Expanded(child: Text(
                  '${a['node_id']} — ${a['status']}',
                  style: const TextStyle(color: Colors.white, fontSize: 11),
                  overflow: TextOverflow.ellipsis,
                )),
              ]),
            )),
          ],
        ]),
      ),
    );
  }
}
