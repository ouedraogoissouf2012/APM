/// A guided conversation scenario. `id` is sent to the backend as `scenario_id`
/// and drives the AI's role in the prompt.
class Scenario {
  const Scenario({
    required this.id,
    required this.title,
    required this.description,
    required this.emoji,
  });

  final String id;
  final String title;
  final String description;
  final String emoji;
}

const List<Scenario> kScenarios = [
  Scenario(
    id: 'restaurant',
    title: 'At a restaurant',
    description: 'Order food and chat with a waiter.',
    emoji: '🍽️',
  ),
  Scenario(
    id: 'job_interview',
    title: 'Job interview',
    description: 'Practise answering interview questions.',
    emoji: '💼',
  ),
  Scenario(
    id: 'travel',
    title: 'Traveling',
    description: 'Ask for directions and book a hotel.',
    emoji: '✈️',
  ),
  Scenario(
    id: 'small_talk',
    title: 'Small talk',
    description: 'Casual, everyday conversation.',
    emoji: '💬',
  ),
  Scenario(
    id: 'shopping',
    title: 'Shopping',
    description: 'Buy clothes and ask about prices.',
    emoji: '🛍️',
  ),
];
