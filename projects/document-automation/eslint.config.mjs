// ESLint flat config: code only. data/ holds the invented sample person, output/ the generated files; neither is linted.
import js from '@eslint/js';
import globals from 'globals';

export default [
  { ignores: ['node_modules/**', 'data/**', 'output/**', '**/*.html'] },
  {
    files: ['*.js', 'src/**/*.js', 'test/**/*.js'],
    ...js.configs.recommended,
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'commonjs',
      globals: { ...globals.node },
    },
  },
];
