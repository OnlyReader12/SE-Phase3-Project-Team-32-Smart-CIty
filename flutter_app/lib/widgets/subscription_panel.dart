import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';
import '../providers/dashboard_provider.dart';

/// Subscription zone + domain picker for Resident dashboard.
/// Shows all available zones from /nodes/browse and lets users subscribe/unsubscribe.
class SubscriptionPanel extends ConsumerStatefulWidget {
  const SubscriptionPanel({super.key});
  @override
  ConsumerState<SubscriptionPanel> createState() => _SubscriptionPanelState();
}

class _SubscriptionPanelState extends ConsumerState<SubscriptionPanel> {
  final Set<String> _zones   = {};
  final Set<String> _domains = {};
  bool _alertInApp  = true;
  bool _alertSms    = false;
  bool _alertEmail  = false;
  bool _saving = false;
  String? _existingSubId;
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _loadExisting();
  }

  Future<void> _loadExisting() async {
    try {
      final subs = await ref.read(subscriptionsProvider.future);
      if (subs.isNotEmpty) {
        final sub = subs.first;
        _existingSubId = sub['id'];
        setState(() {
          _zones.addAll((sub['zone_ids'] as List).cast<String>());
          _domains.addAll((sub['engine_types'] as List).cast<String>());
          _alertInApp = sub['alert_in_app'] ?? true;
          _alertSms   = sub['alert_sms']   ?? false;
          _alertEmail = sub['alert_email'] ?? false;
        });
      }
    } catch (_) {}
  }

  Future<void> _save() async {
    if (_zones.isEmpty || _domains.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Select at least 1 zone and 1 domain')));
      return;
    }
    setState(() => _saving = true);
    final body = {
      'zone_ids':     _zones.toList(),
      'engine_types': _domains.toList(),
      'alert_in_app': _alertInApp,
      'alert_sms':    _alertSms,
      'alert_email':  _alertEmail,
    };
    try {
      if (_existingSubId != null) {
        await ApiClient.instance.put('/resident/subscriptions/$_existingSubId', data: body);
      } else {
        final resp = await ApiClient.instance.post('/resident/subscriptions', data: body);
        _existingSubId = resp.data['id'];
      }
      ref.invalidate(subscriptionsProvider);
      ref.invalidate(residentDashboardProvider);
      ref.invalidate(myNodesProvider);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Subscription saved ✓'),
              backgroundColor: Color(0xFF166534)));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Save failed: $e'),
              backgroundColor: const Color(0xFF7F1D1D)));
    }
    setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    final catalogAsync = ref.watch(nodeCatalogProvider);

    return Card(
      color: const Color(0xFF1E293B),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Header
          Row(children: [
            const Icon(Icons.tune, color: Color(0xFF38BDF8), size: 18),
            const SizedBox(width: 8),
            const Text('My Subscriptions',
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            const Spacer(),
            _saving
                ? const SizedBox(width: 20, height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : ElevatedButton.icon(
                    icon: const Icon(Icons.save, size: 14),
                    label: const Text('Save', style: TextStyle(fontSize: 12)),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF0369A1),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    ),
                    onPressed: _save,
                  ),
          ]),
          const SizedBox(height: 14),

          // Domain filters
          const Text('Filter by Domain',
              style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
          const SizedBox(height: 6),
          Row(children: [
            _domainChip('energy', '⚡ Energy', const Color(0xFFFBBF24)),
            const SizedBox(width: 8),
            _domainChip('water', '💧 Water', const Color(0xFF38BDF8)),
            const SizedBox(width: 8),
            _domainChip('air', '🌬 Air', const Color(0xFF4ADE80)),
            const Spacer(),
            TextButton(
              onPressed: () => setState(() => _domains.clear()),
              child: const Text('Clear', style: TextStyle(color: Color(0xFF64748B), fontSize: 11)),
            ),
          ]),
          const SizedBox(height: 14),

          // Search bar
          Row(children: [
            Expanded(
              child: TextField(
                style: const TextStyle(color: Colors.white, fontSize: 13),
                decoration: InputDecoration(
                  hintText: 'Search zones…',
                  hintStyle: const TextStyle(color: Color(0xFF64748B)),
                  prefixIcon: const Icon(Icons.search, size: 18, color: Color(0xFF64748B)),
                  filled: true,
                  fillColor: const Color(0xFF0F172A),
                  contentPadding: const EdgeInsets.symmetric(vertical: 8),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide.none,
                  ),
                ),
                onChanged: (v) => setState(() => _searchQuery = v.toLowerCase()),
              ),
            ),
            const SizedBox(width: 8),
            catalogAsync.when(
              data: (catalog) {
                final filtered = (catalog['zones'] as List? ?? [])
                    .cast<Map<String, dynamic>>()
                    .where((z) {
                      final zId = (z['zone_id'] as String? ?? '').toLowerCase();
                      return _searchQuery.isEmpty || zId.contains(_searchQuery);
                    }).toList();
                return TextButton(
                  onPressed: () {
                    setState(() {
                      for (final z in filtered) {
                        _zones.add(z['zone_id']);
                      }
                    });
                  },
                  child: const Text('Select All', style: TextStyle(color: Color(0xFF38BDF8), fontSize: 11)),
                );
              },
              loading: () => const SizedBox(),
              error: (_, __) => const SizedBox(),
            ),
          ]),
          const SizedBox(height: 14),

          // Zone list from catalog
          const Text('Available Zones',
              style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
          const SizedBox(height: 6),
          catalogAsync.when(
            loading: () => const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            ),
            error: (e, _) => Text('Could not load zones: $e',
                style: const TextStyle(color: Color(0xFF64748B), fontSize: 12)),
            data: (catalog) {
              final zones = (catalog['zones'] as List? ?? [])
                  .cast<Map<String, dynamic>>()
                  .where((z) {
                    final zId = (z['zone_id'] as String? ?? '').toLowerCase();
                    final matchesSearch = _searchQuery.isEmpty || zId.contains(_searchQuery);
                    final matchesDomain = _domains.isEmpty ||
                        (z['domains'] as List? ?? []).any((d) => _domains.contains(d));
                    return matchesSearch && matchesDomain;
                  }).toList();

              if (zones.isEmpty) {
                return const Text('No zones found.',
                    style: TextStyle(color: Color(0xFF64748B), fontSize: 12));
              }

              return Wrap(
                spacing: 8,
                runSpacing: 8,
                children: zones.map((z) {
                  final zoneId   = z['zone_id'] as String;
                  final domains  = (z['domains'] as List? ?? []).cast<String>();
                  final nodeCount = z['node_count'] as int? ?? 0;
                  final selected = _zones.contains(zoneId);

                  return GestureDetector(
                    onTap: () => setState(() =>
                        selected ? _zones.remove(zoneId) : _zones.add(zoneId)),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: selected
                            ? const Color(0xFF0369A1).withOpacity(0.2)
                            : const Color(0xFF0F172A),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: selected
                              ? const Color(0xFF38BDF8)
                              : const Color(0xFF334155),
                          width: selected ? 2 : 1,
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(children: [
                            Icon(
                              selected ? Icons.check_circle : Icons.location_on_outlined,
                              color: selected
                                  ? const Color(0xFF38BDF8)
                                  : const Color(0xFF64748B),
                              size: 14,
                            ),
                            const SizedBox(width: 6),
                            Text(zoneId,
                                style: TextStyle(
                                  color: selected ? Colors.white : const Color(0xFF94A3B8),
                                  fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                                  fontSize: 12,
                                )),
                          ]),
                          const SizedBox(height: 4),
                          Row(children: [
                            Text('$nodeCount nodes',
                                style: const TextStyle(
                                    color: Color(0xFF64748B), fontSize: 10)),
                            const SizedBox(width: 6),
                            ...domains.map((d) => _domainDot(d)),
                          ]),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              );
            },
          ),
          const SizedBox(height: 14),

          // Alert preferences
          const Text('Alert Preferences',
              style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
          _alertToggle('In-App 🔔', _alertInApp,
              (v) => setState(() => _alertInApp = v)),
          _alertToggle('SMS 📱',    _alertSms,
              (v) => setState(() => _alertSms = v)),
          _alertToggle('Email 📧',  _alertEmail,
              (v) => setState(() => _alertEmail = v)),

          // Summary
          if (_zones.isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF0F172A),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'Subscribed to: ${_zones.join(", ")}  |  ${_domains.join(", ")}',
                style: const TextStyle(color: Color(0xFF38BDF8), fontSize: 11),
              ),
            ),
          ],
        ]),
      ),
    );
  }

  Widget _domainChip(String id, String label, Color color) {
    final selected = _domains.contains(id);
    return FilterChip(
      label: Text(label, style: TextStyle(fontSize: 11,
          color: selected ? Colors.white : const Color(0xFF94A3B8))),
      selected: selected,
      selectedColor: color.withOpacity(0.2),
      backgroundColor: const Color(0xFF0F172A),
      checkmarkColor: color,
      side: BorderSide(color: selected ? color : const Color(0xFF334155)),
      onSelected: (v) => setState(() => v ? _domains.add(id) : _domains.remove(id)),
    );
  }

  Widget _domainDot(String domain) {
    final colors = {'energy': const Color(0xFFFBBF24),
                    'water': const Color(0xFF38BDF8),
                    'air': const Color(0xFF4ADE80)};
    final color = colors[domain] ?? Colors.grey;
    return Container(
      width: 6, height: 6,
      margin: const EdgeInsets.only(right: 3),
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }

  Widget _alertToggle(String label, bool value, ValueChanged<bool> onChanged) {
    return Row(children: [
      Switch(value: value, activeColor: const Color(0xFF38BDF8), onChanged: onChanged),
      Text(label, style: const TextStyle(color: Colors.white, fontSize: 12)),
    ]);
  }
}
