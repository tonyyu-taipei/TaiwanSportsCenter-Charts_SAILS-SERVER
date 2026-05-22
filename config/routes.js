/**
 * Route Mappings
 * (sails.config.routes)
 *
 * Your routes tell Sails what to do each time it receives a request.
 *
 * For more information on configuring custom routes, check out:
 * https://sailsjs.com/anatomy/config/routes-js
 */

module.exports.routes = {
  'GET /': 'home/index',
  'GET /data/date': {
    controller: 'DataController',
    action: 'date'
  },
  'GET /data/date1': {
    controller: 'DataController',
    action: 'date1'
  },
  'GET /data/prediction': {
    controller: 'DataController',
    action: 'prediction'
  },
  'GET /data': { action: 'data/find' },
  'GET /locations': { action: 'locations/find' }
};
