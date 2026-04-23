import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api_client.dart';

/// Reusable actuator toggle — sends PATCH /actuators/{nodeId}/command.
/// Shows ON/OFF switch with loading state and success/error snackbar.
class ActuatorToggle extends ConsumerStatefulWidget {
  final String nodeId;
  final String label;
  const ActuatorToggle({super.key, required this.nodeId, required this.label});

  @override
  ConsumerState<ActuatorToggle> createState() => _ActuatorToggleState();
}

class _ActuatorToggleState extends ConsumerState<ActuatorToggle> {
  bool _isOn      = false;
  bool _loading   = false;

  Future<void> _toggle() async {
    setState(() => _loading = true);

    final newValue = _isOn ? 'OFF' : 'ON';
    try {
      await ApiClient.instance.patch(
        '/actuators/${widget.nodeId}/command',
        data: {'field': 'state', 'value': newValue},
      );
      setState(() { _isOn = !_isOn; _loading = false; });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: const Color(0xFF166534),
          content: Text('${widget.nodeId} → $newValue',
              style: const TextStyle(color: Colors.white)),
          duration: const Duration(seconds: 2),
        ));
      }
    } catch (e) {
      setState(() => _loading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: const Color(0xFF7F1D1D),
          content: Text('Command failed: $e',
              style: const TextStyle(color: Colors.white)),
          duration: const Duration(seconds: 3),
        ));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(
          Icons.power_settings_new,
          color: _isOn ? const Color(0xFF4ADE80) : const Color(0xFF64748B),
        ),
        title: Text(widget.label,
            style: const TextStyle(color: Colors.white, fontSize: 14)),
        subtitle: Text(widget.nodeId,
            style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
        trailing: _loading
            ? const SizedBox(width: 24, height: 24,
                child: CircularProgressIndicator(strokeWidth: 2))
            : Switch(
                value: _isOn,
                activeColor: const Color(0xFF38BDF8),
                onChanged: (_) => _toggle(),
              ),
      ),
    );
  }
}
