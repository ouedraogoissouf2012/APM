# LiveKit — parking (#506)

LiveKit Agents (WebRTC full-duplex) n'est **pas** une feature a lancer.

Le chemin voix livre est : STT appareil → `POST /sessions/{id}/turn/stream` →
TTS appareil. `VOICE_ENGINE=livekit` est refuse au demarrage.

Ne pas ajouter `livekit-api`, de jetons de room, ni un client Flutter LiveKit
tant que le tour-par-tour n'a pas ete fluide ~30 jours avec de vrais
apprenants. Reevaluer apres Horizon 1.
