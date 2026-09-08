/**
 * DataController
 *
 * @description :: Server-side actions for handling incoming requests.
 * @help        :: See https://sailsjs.com/docs/concepts/actions
 */

//const Data = require("../models/Data");
const { isSameDay, startOfDay, endOfDay } = require('date-fns')
function dateFilter(input,params){ // import the object from the database and the request.
  let resultObj = [];
  let reqTime = new Date(params);

  input.forEach(data => {
    let dataTime = new Date(data.time);
    if(isSameDay(reqTime,dataTime)){
      resultObj.push(data);
    }

  });

  return resultObj;
}
module.exports = {
  Date: async function(req,res){
    let db;
    try {
      db = Data.getDatastore().manager;
    } catch (e) {
      // Datastore manager failed/disconnected
    }

    if (!db) {
      return res.status(500).json({ error: 'database not available' });
    }

    if(req.param('date')){
      let query = {time:{ $gt: new Date(startOfDay(new Date(req.param('date')))), $lt: new Date(endOfDay(new Date(req.param('date')))) }}
      try {
        const result = await db.collection(Data.tableName).find(query).toArray();
        return res.json(result);
      } catch (err) {
        return res.status(500).json({ error: 'database error', details: err });
      }
    }else{
      const pipeline = [
        {
          $addFields: {
            taiwanTime: { $add: ['$time', 8 * 60 * 60 * 1000] }
          }
        },
        {
          $group: {
            _id: { $dateToString: { format: '%Y-%m-%d', date: '$taiwanTime' } },
            firstTime: { $first: '$time' }
          }
        },
        {
          $project: {
            _id: 0,
            time: '$firstTime'
          }
        },
        { $sort: { time: 1 } }
      ];
      try {
        const result = await db.collection(Data.tableName).aggregate(pipeline).toArray();
        const allDate = result.map(doc => doc.time);
        return res.json(allDate);
      } catch (err) {
        return res.status(500).json({ error: 'database error', details: err });
      }
    }
  },
  Date1: async function(req,res){
    try {
      const result = await Data.find({});
      if(req.param('date')) {
        return res.json(dateFilter(result,req.param('date')));
      } else {
        let allDate = result.map(data => data.time);
        return res.json(allDate);
      }
    } catch (err) {
      return res.status(500).json({error:"database error"});
    }
  },

  prediction: async function(req, res) {
    const fs = require('fs');
    const path = require('path');
    
    const getBackupPredictions = (dateStr) => {
      const backupPath = path.join(sails.config.appPath, 'Python', 'predictions_backup.json');
      if (!fs.existsSync(backupPath)) {
        return null;
      }
      try {
        const raw = fs.readFileSync(backupPath, 'utf-8');
        const records = JSON.parse(raw);
        if (!dateStr) {
          const dates = new Set();
          records.forEach(r => {
            if (r.time) {
              const d = r.time.split('T')[0];
              dates.add(d);
            }
          });
          return Array.from(dates).sort().map(d => new Date(d));
        }
        const targetStart = new Date(startOfDay(new Date(dateStr)));
        const targetEnd = new Date(endOfDay(new Date(dateStr)));
        return records.filter(r => {
          const t = new Date(r.time);
          return t >= targetStart && t <= targetEnd;
        }).map(r => ({
          time: new Date(r.time),
          locationPeople: r.locationPeople
        }));
      } catch (err) {
        sails.log.error('Failed to parse predictions backup JSON:', err);
        return null;
      }
    };

    if (req.param('date')) {
      const query = {
        time: {
          $gte: new Date(startOfDay(new Date(req.param('date')))),
          $lte: new Date(endOfDay(new Date(req.param('date'))))
        }
      };
      
      let db;
      try {
        db = Data.getDatastore().manager;
      } catch (e) {
        // Datastore manager failed/disconnected
      }

      if (!db) {
        const backup = getBackupPredictions(req.param('date'));
        if (backup) {
          return res.json(backup);
        }
        return res.json([]);
      }

      try {
        const result = await db.collection('predictions').find(query).toArray();
        if (!result || result.length === 0) {
          const backup = getBackupPredictions(req.param('date'));
          if (backup) {
            return res.json(backup);
          }
          return res.json([]);
        }
        return res.json(result);
      } catch (err) {
        const backup = getBackupPredictions(req.param('date'));
        if (backup) {
          return res.json(backup);
        }
        return res.status(500).json({ error: 'database error', details: err });
      }
    } else {
      let db;
      try {
        db = Data.getDatastore().manager;
      } catch (e) {
        // Datastore manager failed/disconnected
      }

      if (!db) {
        const backup = getBackupPredictions();
        if (backup) {
          return res.json(backup);
        }
        return res.json([]);
      }

      const pipeline = [
        {
          $addFields: {
            taiwanTime: { $add: ['$time', 8 * 60 * 60 * 1000] }
          }
        },
        {
          $group: {
            _id: { $dateToString: { format: '%Y-%m-%d', date: '$taiwanTime' } },
            firstTime: { $first: '$time' }
          }
        },
        {
          $project: {
            _id: 0,
            time: '$firstTime'
          }
        },
        { $sort: { time: 1 } }
      ];
      
      try {
        const result = await db.collection('predictions').aggregate(pipeline).toArray();
        if (!result || result.length === 0) {
          const backup = getBackupPredictions();
          if (backup) {
            return res.json(backup);
          }
          return res.json([]);
        }
        const allDates = result.map(doc => doc.time);
        return res.json(allDates);
      } catch (err) {
        const backup = getBackupPredictions();
        if (backup) {
          return res.json(backup);
        }
        return res.status(500).json({ error: 'database error', details: err });
      }
    }
  },

  accuracy: async function (req, res) {
    const fs = require('fs');
    const path = require('path');
    const testDays = parseInt(req.param('days') || '7', 10);

    const getBackupEvaluation = (days) => {
      const backupPathDays = path.join(sails.config.appPath, 'Python', `accuracy_evaluation_${days}.json`);
      const backupPathDefault = path.join(sails.config.appPath, 'Python', 'accuracy_evaluation.json');
      try {
        if (days && fs.existsSync(backupPathDays)) {
          const raw = fs.readFileSync(backupPathDays, 'utf-8');
          return JSON.parse(raw);
        }
        if (fs.existsSync(backupPathDefault)) {
          const raw = fs.readFileSync(backupPathDefault, 'utf-8');
          return JSON.parse(raw);
        }
      } catch (e) {
        sails.log.error('Failed to read accuracy_evaluation backup JSON:', e);
      }
      return null;
    };

    let db;
    try {
      db = Data.getDatastore().manager;
    } catch (e) {
      // Datastore manager failed/disconnected
    }

    if (!db) {
      const backup = getBackupEvaluation(testDays);
      if (backup) {
        return res.json(backup);
      }
      return res.status(500).json({ error: 'database not available and no backup found' });
    }

    try {
      // 嘗試從 MongoDB accuracy_evaluation collection 讀取評估快照
      const record = await db.collection('accuracy_evaluation').findOne(
        { testDays: testDays },
        { sort: { evaluatedAt: -1 } }
      );

      if (record) {
        delete record._id;
        return res.json(record);
      }

      // 如果找不到特定天數，抓取最新的一筆評估紀錄
      const latest = await db.collection('accuracy_evaluation').findOne(
        {},
        { sort: { evaluatedAt: -1 } }
      );

      if (latest) {
        delete latest._id;
        return res.json(latest);
      }

      // 若 DB 尚未產生紀錄，讀取本地備份
      const backup = getBackupEvaluation(testDays);
      if (backup) {
        return res.json(backup);
      }

      return res.status(404).json({
        message: 'No accuracy evaluation data available yet. Please trigger evaluate_accuracy.py first.'
      });
    } catch (err) {
      const backup = getBackupEvaluation(testDays);
      if (backup) {
        return res.json(backup);
      }
      return res.status(500).json({ error: 'database error', details: err });
    }
  }
};
