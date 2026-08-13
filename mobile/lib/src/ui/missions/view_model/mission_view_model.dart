import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../core/observability/ref_report_error.dart';
import '../../../data/models/mission.dart';
import '../../../data/repositories/mission_repository.dart';

final missionRepositoryProvider = Provider<MissionRepository>(
  (ref) => MissionRepository(ref.watch(authenticatedApiClientProvider)),
);

final missionViewModelProvider =
    NotifierProvider<MissionViewModel, MissionState>(MissionViewModel.new);

enum MissionStatus { idle, compiling, ready, failed }

class MissionState {
  const MissionState({
    this.sourceType = MissionSourceType.offer,
    this.status = MissionStatus.idle,
    this.mission,
  });

  final MissionSourceType sourceType;
  final MissionStatus status;
  final Mission? mission;

  MissionState copyWith({
    MissionSourceType? sourceType,
    MissionStatus? status,
    Mission? mission,
    bool clearMission = false,
  }) => MissionState(
    sourceType: sourceType ?? this.sourceType,
    status: status ?? this.status,
    mission: clearMission ? null : (mission ?? this.mission),
  );
}

/// Drives the "New mission" flow: pick a source type, paste the real document,
/// compile it into a simulation brief (persona/goal/likely questions).
class MissionViewModel extends Notifier<MissionState> {
  @override
  MissionState build() => const MissionState();

  void selectSourceType(MissionSourceType type) {
    // Changing the source resets any previously compiled brief so the UI can't
    // show a brief that no longer matches the selected type.
    state = state.copyWith(
      sourceType: type,
      status: MissionStatus.idle,
      clearMission: true,
    );
  }

  /// Compiles [content] into a mission brief. Returns true on success. A blank
  /// input is rejected locally (no wasted network/LLM call).
  Future<bool> compile(String content) async {
    if (content.trim().isEmpty) return false;
    // Clear any previously compiled brief up front: if this compile fails, the UI
    // must not keep showing (and let the learner launch) a stale brief that no
    // longer matches the current input.
    state = state.copyWith(status: MissionStatus.compiling, clearMission: true);
    try {
      final mission = await ref
          .read(missionRepositoryProvider)
          .compile(sourceType: state.sourceType, content: content.trim());
      state = state.copyWith(status: MissionStatus.ready, mission: mission);
      return true;
    } catch (e, s) {
      // (#351) An unexpected failure here would otherwise vanish silently —
      // report it so a recurring cause (a new backend error shape, a
      // compile-flow regression) is visible instead of just "failed" with
      // no trail.
      ref.reportError(e, s, context: 'MissionViewModel.compile');
      state = state.copyWith(status: MissionStatus.failed);
      return false;
    }
  }
}
