/**
 * Seed Function
 * (sails.config.bootstrap)
 *
 * A function that runs just before your Sails app gets lifted.
 * > Need more flexibility?  You can also create a hook.
 *
 * For more information on seeding your app with fake data, check out:
 * https://sailsjs.com/config/bootstrap
 */

module.exports.bootstrap = async function() {

  // By convention, this is a good place to set up fake data during development.
  //
  // For example:
  // ```
  // // Set up fake development data (or if we already have some, avast)
  // if (await User.count() > 0) {
  //   return;
  // }
  //
  // await User.createEach([
  //   { emailAddress: 'ry@example.com', fullName: 'Ryan Dahl', },
  //   { emailAddress: 'rachael@example.com', fullName: 'Rachael Shaw', },
  //   // etc.
  // ]);
  // ```

  const { spawn } = require('child_process');
  const path = require('path');

  function runRetrainingPipeline() {
    sails.log.info('Triggering XGBoost gym occupancy retraining pipeline...');
    const pythonScript = path.join(sails.config.appPath, 'Python', 'train_predict.py');
    
    // Check if custom python binary is specified in environment variables (e.g. from virtual env), else fallback to python3
    const pythonBin = process.env.PYTHON_BIN || 'python3';
    sails.log.info(`Spawning Python process with binary: ${pythonBin}`);
    const child = spawn(pythonBin, [pythonScript]);
    
    child.stdout.on('data', (data) => {
      sails.log.debug(`[XGBoost Pipeline STDOUT]: ${data.toString().trim()}`);
    });
    
    child.stderr.on('data', (data) => {
      sails.log.error(`[XGBoost Pipeline STDERR]: ${data.toString().trim()}`);
    });
    
    child.on('close', (code) => {
      if (code === 0) {
        sails.log.info('XGBoost gym occupancy prediction retraining completed successfully.');
      } else {
        sails.log.error(`XGBoost retraining pipeline failed with exit code ${code}.`);
      }
    });
  }

  // Execute pipeline asynchronously on server lift
  runRetrainingPipeline();

  // Schedule to run every 12 hours (12 * 60 * 60 * 1000 ms)
  setInterval(runRetrainingPipeline, 12 * 60 * 60 * 1000);

};
