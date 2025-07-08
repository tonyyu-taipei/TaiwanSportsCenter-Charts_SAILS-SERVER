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
    if(req.param('date')){


      let query = {time:{ $gt: new Date(startOfDay(new Date(req.param('date')))), $lt: new Date(endOfDay(new Date(req.param('date')))) }}
      let db = Data.getDatastore().manager;

      db.collection(Data.tableName).find(query).toArray((err, result)=>{
        if(err){
          res.send(500, { error: 'database error' });
          res.end();
        }else{
          res.send(result);
          res.end();
        }
      });
    }else{
      const db = Data.getDatastore().manager;
      const pipeline = [
        {
          $group: {
            _id: { $dateToString: { format: '%Y-%m-%d', date: '$time' } },
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
      db.collection(Data.tableName).aggregate(pipeline).toArray((err, result)=>{
        if(err) {
          res.send(500,{error:'database error',err});
          return res.end();
        }
        const allDate = result.map(doc => doc.time);
        res.send(allDate);
        res.end();
      });
    }
  },
  Date1: async function(req,res){
    Data.find({}).exec((err,result)=>{
      if(req.param('date'))
        res.send(dateFilter(result,req.param('date')))
      else{
      if(err)res.send(500,{error:"database error"})
      let allDate = [];
      result.forEach(data=>{
        allDate.push(data.time)
      })
      res.send(allDate)
    }
      res.end()
    })
 
  }

};

