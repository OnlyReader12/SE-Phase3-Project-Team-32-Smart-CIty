import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';

// ── Dashboard data providers ───────────────────────────────────────────────

final residentDashboardProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/dashboard/resident');
  return resp.data as Map<String, dynamic>;
});

final analystDashboardProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/dashboard/analyst');
  return resp.data as Map<String, dynamic>;
});

final servicerDashboardProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/dashboard/servicer');
  return resp.data as Map<String, dynamic>;
});

final managerTeamProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/dashboard/manager/team');
  return resp.data as Map<String, dynamic>;
});

final managerNodesProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/manager/nodes');
  return (resp.data['nodes'] as List).cast<Map<String, dynamic>>();
});

final alertFeedProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/dashboard/alerts');
  return (resp.data['alerts'] as List).cast<Map<String, dynamic>>();
});

// ── Subscriptions ──────────────────────────────────────────────────────────

final subscriptionsProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/resident/subscriptions');
  return (resp.data as List).cast<Map<String, dynamic>>();
});

// ── Servicer assignments ───────────────────────────────────────────────────

final myAssignmentsProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/servicer/assignments');
  return (resp.data as List).cast<Map<String, dynamic>>();
});

// ── Node state (for actuator) ──────────────────────────────────────────────

final nodeStateProvider = FutureProvider.autoDispose.family<Map<String, dynamic>, String>(
  (ref, nodeId) async {
    final resp = await ApiClient.instance.get('/actuators/$nodeId/state');
    return resp.data as Map<String, dynamic>;
  },
);

// ── My nodes (role-scoped) ─────────────────────────────────────────────────

final myNodesProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/nodes/my');
  return (resp.data as List).cast<Map<String, dynamic>>();
});

// ── Node zone catalog (for Resident subscription) ──────────────────────────

final nodeCatalogProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/nodes/browse');
  return resp.data as Map<String, dynamic>;
});

final zoneNodesProvider = FutureProvider.autoDispose.family<List<Map<String, dynamic>>, String>(
  (ref, zoneId) async {
    final resp = await ApiClient.instance.get('/nodes/browse/$zoneId');
    return (resp.data as List).cast<Map<String, dynamic>>();
  },
);

// ── Node history (time-series) ─────────────────────────────────────────────

final nodeHistoryProvider = FutureProvider.autoDispose.family<Map<String, dynamic>, String>(
  (ref, nodeId) async {
    final resp = await ApiClient.instance.get('/nodes/$nodeId/history?limit=50');
    return resp.data as Map<String, dynamic>;
  },
);

// ── Notifications (alerts/my) ──────────────────────────────────────────────

final notificationCountProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/alerts/unread-count');
  return (resp.data['unread'] as int?) ?? 0;
});

final myAlertsProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/alerts/my?acknowledged=false');
  return (resp.data as List).cast<Map<String, dynamic>>();
});

final myAlertsAllProvider = FutureProvider.autoDispose((ref) async {
  final resp = await ApiClient.instance.get('/alerts/my');
  return (resp.data as List).cast<Map<String, dynamic>>();
});
