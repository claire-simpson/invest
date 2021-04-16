const { ipcRenderer } = require('electron'); // eslint-disable-line import/no-extraneous-dependencies

const { getLogger } = require('./logger');
const logger = getLogger(__filename.split('/').slice(-1)[0]);

const isDevMode = process.argv.includes('--dev');
if (isDevMode) {
  // in dev mode we can have babel transpile modules on import
  require('@babel/register'); // eslint-disable-line import/no-extraneous-dependencies
  // load the '.env' file from the project root
  const dotenv = require('dotenv'); // eslint-disable-line import/no-extraneous-dependencies
  dotenv.config();
  require('react-devtools');
}

const _interopRequireDefault = require('@babel/runtime/helpers/interopRequireDefault');
const react = _interopRequireDefault(require('react'));
const reactDom = _interopRequireDefault(require('react-dom'));
logger.debug('after indexjs react requires')
const app = require('./app');
logger.debug('after app.jsx require')

// Create a right-click menu
// TODO: Not sure if Inspect Element should be available in production
// very useful in dev though.
let rightClickPosition = null;
window.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  rightClickPosition = { x: e.x, y: e.y };
  ipcRenderer.invoke('show-context-menu', rightClickPosition);
});

const render = async function render(investExe, isFirstRun) {
  reactDom.default.render(
    react.default.createElement(
      app.default, {
        investExe: investExe,
        isFirstRun: isFirstRun,
      }
    ),
    document.getElementById('App')
  );
};

logger.debug('invoking variable request from main')
ipcRenderer.invoke('variable-request')
  // render the App after receiving any critical data
  // from the main process
  .then((response) => {
    logger.debug('rendering react on response from main')
    render(response.investExe, response.isFirstRun);
  });
