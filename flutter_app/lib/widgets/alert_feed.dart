import 'package:flutter/material.dart';

class AlertFeed extends StatelessWidget {
  final List<Map<String, dynamic>> alerts;
  const AlertFeed({super.key, required this.alerts});

  @override
  Widget build(BuildContext context) {
    if (alerts.isEmpty) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(children: [
            const Icon(Icons.check_circle, color: Color(0xFF4ADE80)),
            const SizedBox(width: 10),
            const Text('No active alerts in your zones',
                style: TextStyle(color: Color(0xFF94A3B8))),
          ]),
        ),
      );
    }

    return Column(
      children: alerts.map((a) => _AlertCard(alert: a)).toList(),
    );
  }
}

class _AlertCard extends StatelessWidget {
  final Map<String, dynamic> alert;
  const _AlertCard({required this.alert});

  Color _color(String severity) => switch (severity) {
    'CRITICAL' => const Color(0xFFEF4444),
    'WARNING'  => const Color(0xFFFBBF24),
    _          => const Color(0xFF38BDF8),
  };

  IconData _icon(String? domain) => switch (domain) {
    'energy' => Icons.bolt,
    'water'  => Icons.water_drop,
    'air'    => Icons.air,
    _        => Icons.warning_amber,
  };

  @override
  Widget build(BuildContext context) {
    final severity = alert['severity'] as String? ?? 'INFO';
    final color    = _color(severity);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: color.withOpacity(0.4), width: 1),
      ),
      child: ListTile(
        leading: Icon(_icon(alert['domain']?.toString()), color: color),
        title: Text(alert['message'] ?? '',
            style: const TextStyle(color: Colors.white, fontSize: 13)),
        subtitle: Text(
          '${alert['zone_id']} · ${alert['created_at']?.toString().substring(0, 16) ?? ''}',
          style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11),
        ),
        trailing: Chip(
          label: Text(severity, style: TextStyle(color: color, fontSize: 10)),
          backgroundColor: color.withOpacity(0.1),
          side: BorderSide(color: color.withOpacity(0.3)),
        ),
      ),
    );
  }
}
