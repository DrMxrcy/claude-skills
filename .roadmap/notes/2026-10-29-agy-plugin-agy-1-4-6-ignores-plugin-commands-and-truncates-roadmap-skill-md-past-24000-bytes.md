# agy plugin: agy 1.4.6 ignores plugin commands and truncates roadmap SKILL.md past 24000 bytes

agy plugin validate agy-plugin/plugins/roadmap (agy 1.4.6) passes with 6 warnings: commands are never loaded (agy wants each as skills/<name>/SKILL.md); plugin.json fields commands/hooks/interface/rules are unknown and ignored; skills/roadmap/SKILL.md is 30820 bytes and only the first 24000 load. So /roadmap-* commands and part of the skill body silently don't reach agy users. Needs a plugin restructure (commands as skills, slimmer SKILL.md or split references).
