import 'package:flutter/material.dart';

/// Node list tile used in the Servicer dashboard node list.
class NodeListTile extends StatelessWidget {
  final Map<String, dynamic> node;
  final VoidCallback? onTap;
  const NodeListTile({super.key, required this.node, this.onTap});

  Color _health(String? h, String? s) {
    if (s == 'OFFLINE') return const Color(0xFFEF4444);
    if (h == 'DEGRADED') return const Color(0xFFFBBF24);
    return const Color(0xFF4ADE80);
  }

  @override
  Widget build(BuildContext context) {
    final health = node['health']?.toString();
    final state  = node['state']?.toString();
    final color  = _health(health, state);

    return ListTile(
      onTap: onTap,
      leading: Container(
        width: 12, height: 12,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
      title: Text(node['node_id'] ?? '-',
          style: const TextStyle(color: Colors.white, fontSize: 13,
              fontWeight: FontWeight.w500)),
      subtitle: Text('${node['zone'] ?? '-'} · ${node['node_type'] ?? '-'}',
          style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(state ?? '-', style: TextStyle(color: color, fontSize: 11)),
          Text(health ?? '-',
              style: const TextStyle(color: Color(0xFF64748B), fontSize: 10)),
        ],
      ),
    );
  }
}
