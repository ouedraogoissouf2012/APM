/// A minimal pair: two English words differing by a single sound French speakers
/// commonly confuse. [wordA]/[wordB] are the two words; [sound] labels the target
/// contrast; [tip] is a short articulation cue in French.
class MinimalPair {
  const MinimalPair({
    required this.id,
    required this.wordA,
    required this.wordB,
    required this.sound,
    required this.tip,
  });

  final String id;
  final String wordA;
  final String wordB;
  final String sound;
  final String tip;
}

/// Curated inventory of FR→EN minimal pairs, grouped by the sound contrast that
/// trips French speakers up. Static content (not LLM-generated): the useful pairs
/// are a known, stable set, and a generator would risk inventing false ones.
const List<MinimalPair> kMinimalPairs = [
  // /ɪ/ (court) vs /iː/ (long) — le piège le plus classique.
  MinimalPair(
    id: 'ship_sheep',
    wordA: 'ship',
    wordB: 'sheep',
    sound: '/ɪ/ vs /iː/',
    tip: "Garde la voyelle très courte pour « ship », allonge-la pour « sheep ».",
  ),
  MinimalPair(
    id: 'live_leave',
    wordA: 'live',
    wordB: 'leave',
    sound: '/ɪ/ vs /iː/',
    tip: "« live » est bref ; « leave » étire le « ee ».",
  ),
  MinimalPair(
    id: 'bit_beat',
    wordA: 'bit',
    wordB: 'beat',
    sound: '/ɪ/ vs /iː/',
    tip: "« bit » = court et relâché ; « beat » = long et tendu.",
  ),
  MinimalPair(
    id: 'fill_feel',
    wordA: 'fill',
    wordB: 'feel',
    sound: '/ɪ/ vs /iː/',
    tip: "Souris davantage pour le « ee » long de « feel ».",
  ),
  MinimalPair(
    id: 'sit_seat',
    wordA: 'sit',
    wordB: 'seat',
    sound: '/ɪ/ vs /iː/',
    tip: "« sit » coupe net ; « seat » tient la voyelle.",
  ),

  // /θ/ et /ð/ (th) — inexistants en français.
  MinimalPair(
    id: 'think_sink',
    wordA: 'think',
    wordB: 'sink',
    sound: '/θ/ (th)',
    tip: "Pour « think », la langue touche les dents ; « sink » siffle avec un « s ».",
  ),
  MinimalPair(
    id: 'thin_sin',
    wordA: 'thin',
    wordB: 'sin',
    sound: '/θ/ (th)',
    tip: "Sors un peu la langue entre les dents pour « thin ».",
  ),
  MinimalPair(
    id: 'thick_sick',
    wordA: 'thick',
    wordB: 'sick',
    sound: '/θ/ (th)',
    tip: "« thick » = th soufflé ; « sick » = s simple.",
  ),
  MinimalPair(
    id: 'they_day',
    wordA: 'they',
    wordB: 'day',
    sound: '/ð/ (th sonore)',
    tip: "« they » vibre avec la langue aux dents ; « day » commence par un « d ».",
  ),
  MinimalPair(
    id: 'other_udder',
    wordA: 'other',
    wordB: 'udder',
    sound: '/ð/ (th sonore)',
    tip: "Le « th » sonore de « other » se fait langue entre les dents.",
  ),

  // h aspiré — souvent muet chez les francophones.
  MinimalPair(
    id: 'heat_eat',
    wordA: 'heat',
    wordB: 'eat',
    sound: 'h aspiré',
    tip: "Souffle un « h » avant « heat » ; ne l'oublie pas comme en français.",
  ),
  MinimalPair(
    id: 'hair_air',
    wordA: 'hair',
    wordB: 'air',
    sound: 'h aspiré',
    tip: "« hair » commence par un souffle ; « air » démarre à la voyelle.",
  ),
  MinimalPair(
    id: 'hill_ill',
    wordA: 'hill',
    wordB: 'ill',
    sound: 'h aspiré',
    tip: "Expire nettement le « h » de « hill ».",
  ),
  MinimalPair(
    id: 'high_eye',
    wordA: 'high',
    wordB: 'eye',
    sound: 'h aspiré',
    tip: "« high » a un « h » soufflé ; « eye » n'en a pas.",
  ),
  MinimalPair(
    id: 'hold_old',
    wordA: 'hold',
    wordB: 'old',
    sound: 'h aspiré',
    tip: "Marque le « h » de « hold ».",
  ),

  // /æ/ vs /ɛ/ — deux « a/e » proches.
  MinimalPair(
    id: 'man_men',
    wordA: 'man',
    wordB: 'men',
    sound: '/æ/ vs /ɛ/',
    tip: "« man » ouvre grand la bouche ; « men » est plus fermé.",
  ),
  MinimalPair(
    id: 'bad_bed',
    wordA: 'bad',
    wordB: 'bed',
    sound: '/æ/ vs /ɛ/',
    tip: "« bad » = a très ouvert ; « bed » = e comme « ê ».",
  ),
  MinimalPair(
    id: 'sad_said',
    wordA: 'sad',
    wordB: 'said',
    sound: '/æ/ vs /ɛ/',
    tip: "« sad » ouvre le a ; « said » se dit « sed ».",
  ),

  // /æ/ vs /ʌ/ — a ouvert vs voyelle centrale.
  MinimalPair(
    id: 'cat_cut',
    wordA: 'cat',
    wordB: 'cut',
    sound: '/æ/ vs /ʌ/',
    tip: "« cat » = a franc ; « cut » = son plus sourd, vers « eu ».",
  ),
  MinimalPair(
    id: 'bat_but',
    wordA: 'bat',
    wordB: 'but',
    sound: '/æ/ vs /ʌ/',
    tip: "« bat » ouvre le a ; « but » se relâche vers « eu ».",
  ),

  // /b/ vs /v/ — parfois confondus.
  MinimalPair(
    id: 'berry_very',
    wordA: 'berry',
    wordB: 'very',
    sound: '/b/ vs /v/',
    tip: "« berry » ferme les lèvres ; « very » mord la lèvre inférieure.",
  ),
  MinimalPair(
    id: 'best_vest',
    wordA: 'best',
    wordB: 'vest',
    sound: '/b/ vs /v/',
    tip: "« best » = b des lèvres ; « vest » = v dents sur lèvre.",
  ),

  // /w/ vs /v/.
  MinimalPair(
    id: 'west_vest',
    wordA: 'west',
    wordB: 'vest',
    sound: '/w/ vs /v/',
    tip: "« west » arrondit les lèvres ; « vest » mord la lèvre.",
  ),
  MinimalPair(
    id: 'wine_vine',
    wordA: 'wine',
    wordB: 'vine',
    sound: '/w/ vs /v/',
    tip: "« wine » commence par un « ou » arrondi ; « vine » par un « v ».",
  ),

  // /ɔː/ vs /əʊ/ — o long vs diphtongue.
  MinimalPair(
    id: 'walk_woke',
    wordA: 'walk',
    wordB: 'woke',
    sound: '/ɔː/ vs /əʊ/',
    tip: "« walk » = o long ouvert ; « woke » glisse vers « ow ».",
  ),
  MinimalPair(
    id: 'ball_bowl',
    wordA: 'ball',
    wordB: 'bowl',
    sound: '/ɔː/ vs /əʊ/',
    tip: "« ball » tient le o ; « bowl » diphtongue vers « ôou ».",
  ),

  // -ed final — souvent trop prononcé.
  MinimalPair(
    id: 'walked_walk',
    wordA: 'walked',
    wordB: 'walk',
    sound: '-ed final',
    tip: "Le « -ed » de « walked » se dit /t/, léger, pas « -eud ».",
  ),
  MinimalPair(
    id: 'liked_like',
    wordA: 'liked',
    wordB: 'like',
    sound: '-ed final',
    tip: "« liked » ajoute juste un /t/ discret à la fin.",
  ),

  // /s/ vs /z/ final.
  MinimalPair(
    id: 'ice_eyes',
    wordA: 'ice',
    wordB: 'eyes',
    sound: '/s/ vs /z/',
    tip: "« ice » finit par un « s » ; « eyes » vibre en « z ».",
  ),
  MinimalPair(
    id: 'price_prize',
    wordA: 'price',
    wordB: 'prize',
    sound: '/s/ vs /z/',
    tip: "« price » = s net ; « prize » = z sonore.",
  ),
];
